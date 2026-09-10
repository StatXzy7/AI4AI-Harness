"""Improves a single greedy call by generating initial/direct answers, verifying the leading answer, and selecting the most consistent extracted result."""
import re
from fractions import Fraction

try:
    from ..harness_base import MathHarness
except Exception:
    class MathHarness:
        def llm(self, prompt, system="", temperature=0.0, n=1):
            raise NotImplementedError


class GsmGsmQwenS0G6(MathHarness):
    SYSTEM = (
        "You are a precise competition-math solver. "
        "The final answer may be a number, fraction, LaTeX expression, interval, or tuple. "
        "Always put the final answer on the last line in the exact form '#### <answer>'."
    )

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return ""

        candidates = []

        initial_text = self._safe_llm(self._solve_prompt(question), self.SYSTEM)
        self._add_candidate(candidates, self._extract_answer(initial_text), weight=1.0)

        direct_text = self._safe_llm(self._direct_prompt(question), self.SYSTEM)
        self._add_candidate(candidates, self._extract_answer(direct_text), weight=1.0)

        # If two prompt variants already agree, trust the agreement.
        if len(candidates) >= 2 and len(self._unique_keys(candidates)) == 1:
            return self._choose_best(candidates)

        # Otherwise, verify the current leader with an independent checking prompt.
        if candidates:
            lead = self._choose_best(candidates)
            if lead:
                check_text = self._safe_llm(self._check_prompt(question, lead), self.SYSTEM)
                self._add_candidate(candidates, self._extract_answer(check_text), weight=1.5)
        else:
            fallback_text = self._safe_llm(self._fallback_prompt(question), self.SYSTEM)
            self._add_candidate(candidates, self._extract_answer(fallback_text), weight=1.5)

        # If disagreement remains, ask for a tie-breaking independent solution.
        if len(candidates) >= 2 and len(self._unique_keys(candidates)) > 1:
            displays = []
            seen = set()
            for display, key, _, _ in candidates:
                if key not in seen:
                    seen.add(key)
                    displays.append(display)

            tie_text = self._safe_llm(self._tie_prompt(question, displays), self.SYSTEM)
            self._add_candidate(candidates, self._extract_answer(tie_text), weight=2.0)

        return self._choose_best(candidates)

    def _solve_prompt(self, question: str) -> str:
        return (
            f"{question}\n\n"
            "Solve the problem step by step. Keep the reasoning concise.\n"
            "On the very last line, write the final answer exactly in this form:\n"
            "#### <answer>"
        )

    def _direct_prompt(self, question: str) -> str:
        return (
            f"{question}\n\n"
            "Determine the final answer carefully, without a long explanation.\n"
            "On the very last line, write only:\n"
            "#### <answer>"
        )

    def _check_prompt(self, question: str, answer: str) -> str:
        return (
            f"Question: {question}\n\n"
            f"Proposed answer: {answer}\n\n"
            "Check this proposed answer independently. Recompute the crucial steps or substitute it back. "
            "If it is correct, repeat it. If it is incorrect, give the corrected answer.\n"
            "On the very last line, write only:\n"
            "#### <answer>"
        )

    def _fallback_prompt(self, question: str) -> str:
        return (
            f"{question}\n\n"
            "Provide the final answer.\n"
            "On the very last line, write only:\n"
            "#### <answer>"
        )

    def _tie_prompt(self, question: str, answers) -> str:
        answer_list = "; ".join(answers)
        return (
            f"Question: {question}\n\n"
            f"Candidate answers: {answer_list}\n\n"
            "Solve independently and choose the correct final answer. "
            "If all candidates are wrong, provide the correct answer.\n"
            "On the very last line, write only:\n"
            "#### <answer>"
        )

    def _safe_llm(self, prompt: str, system: str = "") -> str:
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                out = self.llm(prompt)
            except Exception:
                return ""
        except Exception:
            return ""

        if out is None:
            return ""
        if isinstance(out, bytes):
            return out.decode("utf-8", "ignore")
        if isinstance(out, (list, tuple)):
            return "\n".join(str(item) for item in out)

        if isinstance(out, dict):
            for key in ("text", "output", "completion", "answer"):
                if isinstance(out.get(key), str):
                    return out[key]

            choices = out.get("choices")
            if isinstance(choices, (list, tuple)) and choices:
                choice = choices[0]
                if isinstance(choice, str):
                    return choice
                if isinstance(choice, dict):
                    if isinstance(choice.get("text"), str):
                        return choice["text"]
                    message = choice.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        return message["content"]

        return out if isinstance(out, str) else str(out)

    def _add_candidate(self, candidates, answer, weight: float) -> None:
        cleaned = self._clean_answer(answer)
        if not cleaned:
            return

        if cleaned.lower() in {"<answer>", "answer", "final answer", "final", "none", "n/a"}:
            return

        key = self._vote_key(cleaned)
        candidates.append((cleaned, key, float(weight), len(candidates)))

    def _unique_keys(self, candidates):
        return {key for _, key, _, _ in candidates}

    def _choose_best(self, candidates) -> str:
        if not candidates:
            return ""

        scores = {}
        counts = {}
        representatives = {}

        for display, key, weight, idx in candidates:
            scores[key] = scores.get(key, 0.0) + weight
            counts[key] = counts.get(key, 0) + 1

            current = representatives.get(key)
            if current is None:
                representatives[key] = (weight, idx, display)
            else:
                cur_weight, cur_idx, cur_display = current
                if (
                    weight > cur_weight
                    or (weight == cur_weight and idx > cur_idx)
                    or (weight == cur_weight and idx == cur_idx and len(display) < len(cur_display))
                ):
                    representatives[key] = (weight, idx, display)

        best_key = max(
            scores.keys(),
            key=lambda k: (scores[k], counts[k], representatives[k][1], -len(representatives[k][2]))
        )
        return representatives[best_key][2]

    def _vote_key(self, answer: str):
        normalized = self._normalize_for_vote(answer)
        frac = self._as_fraction(normalized)
        if frac is not None:
            return ("num", str(frac))
        return ("str", normalized)

    def _extract_answer(self, text):
        if text is None:
            return None

        text = str(text)
        if not text.strip():
            return None

        # Preferred explicit marker.
        matches = re.findall(r"####\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if not matches:
            matches = re.findall(r"####\s*(.+)", text)
        if matches:
            return self._clean_answer(matches[-1])

        # LaTeX boxed answer.
        boxed = self._extract_boxed(text)
        if boxed:
            return self._clean_answer(boxed)

        # Look near the end for natural-language answer markers.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        tail = "\n".join(lines[-10:])
        phrase_matches = re.findall(
            r"(?i)(?:final\s+answer|answer)\s*(?:is|:|=)?\s*(.+)",
            tail
        )
        if phrase_matches:
            return self._clean_answer(phrase_matches[-1])

        # Last-line fallback.
        if lines:
            candidate = lines[-1]
            candidate = re.sub(r"^\s*[-*]+\s*", "", candidate)
            candidate = re.sub(r"^\s*\d+[.)]\s+", "", candidate)
            return self._clean_answer(candidate)

        return None

    def _extract_boxed(self, text: str):
        if not text:
            return None

        last = None
        for match in re.finditer(r"\\boxed\s*\{", text):
            i = match.end()
            depth = 1

            while i < len(text) and depth > 0:
                ch = text[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                i += 1

            if depth == 0:
                last = text[match.end():i - 1]

        return last

    def _clean_answer(self, answer) -> str:
        if answer is None:
            return ""

        s = str(answer).strip()
        if not s:
            return ""

        # Normalize some Unicode math characters.
        s = s.replace("\u2212", "-")
        s = s.replace("∞", r"\infty")

        # Remove code fences/backticks if present.
        s = re.sub(r"