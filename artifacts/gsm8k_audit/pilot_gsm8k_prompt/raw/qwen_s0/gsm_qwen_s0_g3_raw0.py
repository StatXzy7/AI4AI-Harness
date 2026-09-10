"""Samples a small set of solver completions, majority-votes their extracted numeric answers, and uses a verification tie-breaker when no answer has an insurmountable lead."""

import re
from collections import Counter

try:
    from ..harness_base import MathHarness
except ImportError:
    class MathHarness:
        def llm(self, prompt, system="", temperature=0.0, n=1):
            raise NotImplementedError("LLM backend not available")


_NUMBER_PATTERN = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'

_HASH_RE = re.compile(
    r'####\s*:?\s*\$?\s*(' + _NUMBER_PATTERN + r')',
    re.IGNORECASE,
)

_ANSWER_RE = re.compile(
    r'\b(?:final\s*answer|answer\s*is|answer\s*:|answer\s*=|final\s*result|result\s*is|total\s*is)'
    r'\s*:?\s*\$?\s*(' + _NUMBER_PATTERN + r')',
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(_NUMBER_PATTERN)


class GsmGsmQwenS0G3(MathHarness):
    TEMPERATURES = (0.0, 0.7, 0.8)
    SYSTEM = (
        "You are a careful grade-school math solver. "
        "Solve step by step and finish with the final numeric answer on a line like #### <number>."
    )

    def solve(self, question: str) -> str:
        try:
            return self._solve_inner(question)
        except Exception:
            return "0"

    def _solve_inner(self, question: str) -> str:
        question = (question or "").strip()
        prompt = self._solve_prompt(question)

        answers = []
        greedy_answer = None
        first_valid_answer = None
        max_samples = len(self.TEMPERATURES)

        for idx, temperature in enumerate(self.TEMPERATURES):
            answer, _ = self._sample_answer(prompt, temperature)

            if idx == 0:
                greedy_answer = answer
            if first_valid_answer is None and answer is not None:
                first_valid_answer = answer

            if answer is None:
                continue

            answers.append(answer)
            counts = Counter(answers)
            ranked = counts.most_common()
            top_answer, top_count = ranked[0]
            second_count = ranked[1][1] if len(ranked) > 1 else 0
            remaining = max_samples - (idx + 1)

            if top_count > second_count + remaining:
                return top_answer

        if answers:
            counts = Counter(answers)
            ranked = counts.most_common()

            if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
                return ranked[0][0]

            candidate_answers = [answer for answer, _ in ranked]
            verdict = self._verify_answers(question, candidate_answers)
            if verdict is not None:
                return verdict

            if greedy_answer is not None:
                return greedy_answer
            if first_valid_answer is not None:
                return first_valid_answer
            return ranked[0][0]

        verdict = self._verify_answers(question, [])
        if verdict is not None:
            return verdict

        return "0"

    def _solve_prompt(self, question: str) -> str:
        return (
            "Solve the grade-school math word problem step by step. "
            "Check your arithmetic carefully. "
            "End your response with the final numeric answer on a line beginning with ####.\n\n"
            f"Problem:\n{question}\n\nSolution:\n"
        )

    def _verify_answers(self, question: str, candidates):
        candidate_text = ", ".join(str(candidate) for candidate in candidates) if candidates else "none"
        prompt = (
            "You are checking a grade-school math word problem. "
            "Several candidate numeric answers were produced by previous attempts.\n\n"
            f"Problem:\n{question}\n\n"
            f"Candidate answers: {candidate_text}\n\n"
            "Re-solve the problem carefully from the beginning, verify the arithmetic, "
            "and choose the correct final numeric answer. "
            "Do not rely only on the candidates; compute the answer yourself. "
            "End with a line like #### <number>."
        )
        answer, _ = self._sample_answer(prompt, 0.0)
        return answer

    def _sample_answer(self, prompt: str, temperature: float):
        response = None

        for kwargs in (
            {"system": self.SYSTEM, "temperature": temperature, "n": 1},
            {"temperature": temperature, "n": 1},
            {"system": self.SYSTEM},
            {},
        ):
            try:
                response = self.llm(prompt, **kwargs)
                break
            except TypeError:
                continue
            except Exception:
                return None, ""
        else:
            return None, ""

        text = self._coerce_text(response)
        answer = self._extract_number(text)
        return answer, text

    def _coerce_text(self, response, depth=0) -> str:
        if response is None or depth > 4:
            return ""

        if isinstance(response, str):
            return response

        if isinstance(response, (bytes, bytearray)):
            return response.decode("utf-8", errors="ignore")

        if isinstance(response, (list, tuple, set)):
            return "\n".join(self._coerce_text(item, depth + 1) for item in response)

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "output", "message", "choices"):
                if key in response:
                    return self._coerce_text(response[key], depth + 1)
            return str(response)

        for attr in ("text", "completion", "content", "message"):
            if hasattr(response, attr):
                return self._coerce_text(getattr(response, attr), depth + 1)

        return str(response)

    def _extract_number(self, text: str):
        if not text:
            return None

        text = str(text)

        marker_matches = []
        for rx in (_HASH_RE, _ANSWER_RE):
            for match in rx.finditer(text):
                if match.lastindex and match.group(1):
                    marker_matches.append((match.end(), match.group(1)))

        if marker_matches:
            marker_matches.sort(key=lambda item: item[0], reverse=True)
            for _, raw_number in marker_matches:
                normalized = self._normalize_number(raw_number)
                if normalized is not None:
                    return normalized

        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        for line in reversed(lines[-5:]):
            if re.search(r"\b(answer|result|total|sum)\b", line, re.IGNORECASE):
                numbers = _NUMBER_RE.findall(line)
                for raw_number in reversed(numbers):
                    normalized = self._normalize_number(raw_number)
                    if normalized is not None:
                        return normalized

        numbers = _NUMBER_RE.findall(text)
        for raw_number in reversed(numbers):
            normalized = self._normalize_number(raw_number)
            if normalized is not None:
                return normalized

        return None

    def _normalize_number(self, raw):
        if raw is None:
            return None

        s = str(raw).strip().replace(",", "").replace("$", "").replace(" ", "")
        if not s:
            return None

        if s.startswith("+"):
            s = s[1:]
        if s == "-0":
            s = "0"

        if "." in s:
            try:
                int_part, frac_part = s.split(".", 1)
                if int_part in ("", "+", "-"):
                    int_part = (int_part if int_part in ("+", "-") else "") + "0"
                frac_part = frac_part.rstrip("0")
                s = f"{int_part}.{frac_part}" if frac_part else int_part
            except ValueError:
                pass

        if re.fullmatch(r"[+-]?\d+", s):
            try:
                return str(int(s))
            except ValueError:
                return s

        if re.fullmatch(r"[+-]?\d*\.\d+", s):
            sign = "-" if s.startswith("-") else ""
            body = s.lstrip("+-")
            if "." in body:
                int_part, frac_part = body.split(".", 1)
                try:
                    int_part = str(int(int_part)) if int_part else "0"
                except ValueError:
                    int_part = int_part or "0"

                frac_part = frac_part.rstrip("0")
                if not frac_part:
                    if int_part == "0":
                        return "0"
                    return sign + int_part

                return f"{sign}{int_part}.{frac_part}"

        fallback = re.search(r"[+-]?\d+(?:\.\d+)?", s)
        if fallback:
            return self._normalize_number(fallback.group(0))

        return None