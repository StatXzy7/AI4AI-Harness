"""Improves GSM8K answers by generating two independent prompted solutions, returning early on agreement, and otherwise escalating to a third vote and a judge if consensus fails."""

try:
    from ..harness_base import MathHarness
except Exception:
    class MathHarness:
        def llm(self, prompt, system="", temperature=0.0, n=1):
            return ""

import re
from collections import Counter

_NUMBER = r"[-+]?(?:\$)?(?:\d[\d,]*(?:\.\d+)?|\.\d+)"
_HASH_PATTERN = r"####\s*(" + _NUMBER + r")"
_EXPLICIT_PATTERNS = (
    r"final answer[^0-9+\-.]{0,30}?(" + _NUMBER + r")",
    r"answer is[^0-9+\-.]{0,20}?(" + _NUMBER + r")",
    r"answer\s*:\s*(" + _NUMBER + r")",
    r"result is[^0-9+\-.]{0,20}?(" + _NUMBER + r")",
    r"total is[^0-9+\-.]{0,20}?(" + _NUMBER + r")",
    r"=\s*(" + _NUMBER + r")\s*$",
)


class GsmGsmQwenS0G2(MathHarness):
    _SYSTEM_SOLVER = (
        "You are a careful grade-school math solver. "
        "Always end with the final numeric answer in the format: #### <number>."
    )
    _SYSTEM_JUDGE = (
        "You are a careful mathematical judge. "
        "Choose or compute the correct final numeric answer and end with #### <number>."
    )

    def solve(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return "0"

        standard_text = self._call_llm(self._standard_prompt(q), self._SYSTEM_SOLVER)
        standard_ans = self._extract_answer(standard_text)

        check_text = self._call_llm(self._check_prompt(q), self._SYSTEM_SOLVER)
        check_ans = self._extract_answer(check_text)

        if (
            standard_ans is not None
            and check_ans is not None
            and self._same_number(standard_ans, check_ans)
        ):
            return str(standard_ans)

        concise_text = self._call_llm(self._concise_prompt(q), self._SYSTEM_SOLVER)
        concise_ans = self._extract_answer(concise_text)

        candidates = []
        for ans in (standard_ans, check_ans, concise_ans):
            norm = self._normalize_number(ans)
            if norm is not None:
                candidates.append(norm)

        chosen, has_majority = self._choose(candidates)

        if not has_majority and len(candidates) >= 2:
            judge_text = self._call_llm(self._judge_prompt(q, candidates), self._SYSTEM_JUDGE)
            judge_ans = self._extract_answer(judge_text)
            if judge_ans is not None:
                chosen = self._normalize_number(judge_ans)

        if chosen is None:
            direct_text = self._call_llm(self._direct_prompt(q), self._SYSTEM_SOLVER)
            chosen = self._extract_answer(direct_text)

        if chosen is None:
            chosen = self._extract_answer(q)

        return str(chosen if chosen is not None else "0")

    def _standard_prompt(self, q: str) -> str:
        return (
            "Solve the grade-school math problem step by step.\n"
            "Put the final numeric answer on the last line exactly in this format: #### <number>\n\n"
            f"Problem:\n{q}\n\n"
            "Solution:\n"
        )

    def _check_prompt(self, q: str) -> str:
        return (
            "Solve the grade-school math problem, then check your result by estimating or reversing the arithmetic.\n"
            "If the check fails, correct the answer.\n"
            "Put the final numeric answer on the last line exactly in this format: #### <number>\n\n"
            f"Problem:\n{q}\n\n"
            "Solution and check:\n"
        )

    def _concise_prompt(self, q: str) -> str:
        return (
            "Solve the grade-school math problem by first writing the needed arithmetic or equation.\n"
            "Be concise. Put the final numeric answer on the last line exactly in this format: #### <number>\n\n"
            f"Problem:\n{q}\n\n"
            "Solution:\n"
        )

    def _judge_prompt(self, q: str, candidates) -> str:
        candidate_str = ", ".join(str(c) for c in candidates if c is not None)
        return (
            "Several candidate answers were produced for the same grade-school math problem.\n"
            "Solve the problem carefully and choose the correct numeric answer.\n"
            "Put the final numeric answer on the last line exactly in this format: #### <number>\n\n"
            f"Problem:\n{q}\n\n"
            f"Candidate answers: {candidate_str}\n\n"
            "Final answer:\n"
        )

    def _direct_prompt(self, q: str) -> str:
        return (
            "Give only the final numeric answer for the problem. Do not include words, commas, or units.\n\n"
            f"Problem:\n{q}\n\n"
            "Final number:\n"
        )

    def _call_llm(self, prompt: str, system: str = "") -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                response = self.llm(prompt)
            except Exception:
                return ""
        except Exception:
            return ""

        if response is None:
            return ""

        if isinstance(response, (list, tuple)):
            response = "\n".join(str(item) for item in response)
        elif isinstance(response, dict):
            response = (
                response.get("text")
                or response.get("content")
                or response.get("completion")
                or str(response)
            )
        elif hasattr(response, "text"):
            response = response.text

        return str(response)

    def _extract_answer(self, text):
        s = "" if text is None else str(text)
        if not s.strip():
            return None

        marker_matches = []

        for m in re.finditer(_HASH_PATTERN, s, flags=re.IGNORECASE | re.MULTILINE):
            norm = self._normalize_number(m.group(1))
            if norm is not None:
                marker_matches.append((m.end(), 1, norm))

        for pattern in _EXPLICIT_PATTERNS:
            for m in re.finditer(pattern, s, flags=re.IGNORECASE | re.MULTILINE):
                norm = self._normalize_number(m.group(1))
                if norm is not None:
                    marker_matches.append((m.end(), 0, norm))

        if marker_matches:
            marker_matches.sort(key=lambda item: (item[0], item[1]))
            return marker_matches[-1][2]

        lines = [line.strip() for line in s.splitlines() if line.strip()]
        for line in reversed(lines[-5:]):
            nums = re.findall(_NUMBER, line)
            if nums:
                norm = self._normalize_number(nums[-1])
                if norm is not None:
                    return norm

        nums = re.findall(_NUMBER, s)
        if nums:
            norm = self._normalize_number(nums[-1])
            if norm is not None:
                return norm

        return None

    def _normalize_number(self, value):
        if value is None:
            return None

        s = str(value).strip()
        if not s:
            return None

        s = s.replace(",", "").replace("$", "").replace("%", "").replace(" ", "")

        m = re.search(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)", s)
        if not m:
            return None

        s = m.group(0)

        sign = ""
        if s.startswith("-"):
            sign = "-"
            s = s[1:]
        elif s.startswith("+"):
            s = s[1:]

        if s.startswith("."):
            s = "0" + s

        if "." in s:
            int_part, frac_part = s.split(".", 1)
            int_part = int_part.lstrip("0") or "0"
            frac_part = frac_part.rstrip("0")

            if frac_part:
                result = f"{sign}{int_part}.{frac_part}"
            else:
                result = f"{sign}{int_part}" if int_part != "0" else "0"
        else:
            int_part = s.lstrip("0") or "0"
            result = f"{sign}{int_part}" if int_part != "0" else "0"

        if result == "-0":
            result = "0"

        return result

    def _same_number(self, a, b) -> bool:
        na = self._normalize_number(a)
        nb = self._normalize_number(b)
        return na is not None and nb is not None and na == nb

    def _choose(self, candidates):
        normalized = []
        for c in candidates:
            n = self._normalize_number(c)
            if n is not None:
                normalized.append(n)

        if not normalized:
            return None, False

        counts = Counter(normalized)
        top_value, top_count = counts.most_common(1)[0]

        if top_count >= 2:
            return top_value, True

        return normalized[0], False