"""Uses multiple prompted generations, answer normalization, majority voting, and a verifier tie-breaker to choose the final answer."""
try:
    from ..harness_base import MathHarness
except ImportError:
    class MathHarness:
        def llm(self, prompt, system="", temperature=0.0, n=1):
            return ""

import re
from collections import Counter
from fractions import Fraction


class GsmGsmQwenS0G5(MathHarness):
    def solve(self, question: str) -> str:
        question = (question or "").strip()
        candidates = []
        raw_outputs = []

        for system, user in self._solver_variants(question):
            out = self._call_llm(user, system=system, temperature=0.0)
            raw_outputs.append(out)
            ans = self._clean_answer(self._extract_answer(out))
            if ans and not self._is_placeholder(ans):
                candidates.append((self._normalize_answer(ans), ans))

        if not candidates:
            out = self._call_llm(
                self._answer_only_prompt(question),
                system="You are a concise math solver. Final line: #### <answer>",
                temperature=0.0,
            )
            ans = self._clean_answer(self._extract_answer(out))
            if ans and not self._is_placeholder(ans):
                return self._present_answer(ans)

            for out in raw_outputs:
                ans = self._clean_answer(self._last_nonempty(out))
                if ans and not self._is_placeholder(ans):
                    return self._present_answer(ans)
            return ""

        counts = Counter(norm for norm, _ in candidates if norm)
        if counts:
            top_norm, top_count = counts.most_common(1)[0]
        else:
            top_norm, top_count = "", 0

        if top_count >= 2:
            choices = [raw for norm, raw in candidates if norm == top_norm]
            return self._present_answer(self._prefer_compact(choices))

        if len(candidates) == 1:
            return self._present_answer(candidates[0][1])

        unique = []
        seen = set()
        for norm, raw in candidates:
            key = norm or raw
            if key and key not in seen:
                seen.add(key)
                unique.append(raw)

        verdict = self._call_llm(
            self._verifier_prompt(question, unique[:5]),
            system="You are a meticulous mathematics judge. Final line: #### <answer>",
            temperature=0.0,
        )
        v_ans = self._clean_answer(self._extract_answer(verdict))
        if v_ans and not self._is_placeholder(v_ans):
            v_norm = self._normalize_answer(v_ans)
            choices = [v_ans]
            if v_norm:
                choices.extend(raw for norm, raw in candidates if norm == v_norm)
            return self._present_answer(self._prefer_compact(choices))

        if top_norm:
            choices = [raw for norm, raw in candidates if norm == top_norm]
            if choices:
                return self._present_answer(self._prefer_compact(choices))

        return self._present_answer(self._prefer_compact([raw for _, raw in candidates]))

    def _call_llm(self, prompt, system="", temperature=0.0):
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
            return out if isinstance(out, str) else str(out)
        except Exception:
            return ""

    def _solver_variants(self, question):
        base = (
            "The final answer may be a plain number, a fraction like 3/4, "
            "a LaTeX expression like 2\\sqrt{3}, an interval like (3,4], "
            "or a tuple like (2,5). Put the final answer alone on the last "
            "line exactly as: #### <answer>"
        )
        return [
            (
                "You are an expert competition mathematician. Final line: #### <answer>",
                f"Problem:\n{question}\n\n"
                f"Solve step by step, checking arithmetic and endpoint conditions. {base}",
            ),
            (
                "You are a precise mathematical problem solver. Final line: #### <answer>",
                f"Problem:\n{question}\n\n"
                f"Identify the requested quantity, solve with exact arithmetic, and sanity-check. {base}",
            ),
            (
                "You are a careful mathematical auditor. Final line: #### <answer>",
                f"Problem:\n{question}\n\n"
                f"Solve independently, watch for sign, off-by-one, and endpoint errors. {base}",
            ),
        ]

    def _answer_only_prompt(self, question):
        return (
            f"Problem:\n{question}\n\n"
            "Give only the final answer on the last line as: #### <answer>"
        )

    def _verifier_prompt(self, question, answers):
        cand = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(answers))
        return (
            f"Problem:\n{question}\n\n"
            f"Candidate answers:\n{cand}\n\n"
            "Determine the correct exact answer. If a candidate is correct, choose it. "
            "If none is correct, compute the correct answer. Do not output a candidate number. "
            "Put the final answer alone on the last line exactly as: #### <answer>"
        )

    def _extract_answer(self, text):
        if not text:
            return ""
        text = str(text)

        matches = re.findall(r"(?im)^\s*####\s*(?:<answer>)?\s*(.+?)\s*$", text)
        if matches:
            ans = matches[-1]
            boxed = self._extract_boxed(ans)
            return boxed if boxed else ans

        matches = re.findall(r"(?i)####\s*(?:<answer>)?\s*([^\n]+)", text)
        if matches:
            ans = matches[-1]
            boxed = self._extract_boxed(ans)
            return boxed if boxed else ans

        parts = re.split(r"(?im)^\s*####\s*$", text)
        if len(parts) > 1:
            tail = parts[-1].strip()
            if tail:
                first = self._first_nonempty(tail)
                if first:
                    boxed = self._extract_boxed(first)
                    return boxed if boxed else first

        boxed = self._extract_boxed(text)
        if boxed:
            return boxed

        matches = re.findall(r"(?im)^\s*(?:final\s+answer|answer)\s*[:\-]?\s*(.+?)\s*$", text)
        if matches:
            return matches[-1]

        matches = re.findall(r"(?i)\b(?:final\s+answer|answer)\b\s*(?:is|:|=|-)?\s*([^\n]+)", text)
        if matches:
            return matches[-1]

        return self._last_nonempty(text)

    def _extract_boxed(self, text):
        idx = text.rfind("\\boxed{")
        if idx == -1:
            return ""
        start = idx + len("\\boxed{")
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        if depth == 0:
            return text[start:i - 1].strip()
        return text[start:].strip()

    def _first_nonempty(self, text):
        for line in text.splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    def _last_nonempty(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def _clean_answer(self, s):
        if s is None:
            return ""
        s = str(s).strip()
        if not s:
            return ""

        s = re.sub(r"(?m)^