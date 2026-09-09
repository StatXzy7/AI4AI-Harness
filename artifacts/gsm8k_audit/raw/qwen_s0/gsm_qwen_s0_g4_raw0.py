"""Improves over one greedy call by making several prompted solver attempts, extracting numeric answers, and returning the majority or a verified tie-breaker."""
import re

try:
    from ..harness_base import MathHarness
except Exception:
    class MathHarness:
        def llm(self, prompt, system="", temperature=0.0, n=1):
            raise NotImplementedError


class GsmGsmQwenS0G4(MathHarness):
    _NUM = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
    _NUM_RE = re.compile(_NUM)

    _STRONG_ANSWER_PATTERNS = [
        re.compile(
            r'^\s*####\s*:?\s*\$?\s*(' + _NUM + r')\s*\.?\s*$',
            re.IGNORECASE | re.MULTILINE,
        ),
        re.compile(
            r'(?:final\s*answer|the\s*answer|answer)\s*(?:is|was)?\s*[:=]?\s*\$?\s*(' + _NUM + r')',
            re.IGNORECASE,
        ),
        re.compile(
            r'\\boxed\{([^{}]*)\}',
            re.IGNORECASE,
        ),
    ]

    _WEAK_ANSWER_PATTERNS = [
        re.compile(
            r'\b(?:equals|=)\s*\$?\s*(' + _NUM + r')',
            re.IGNORECASE,
        ),
    ]

    def solve(self, question: str) -> str:
        q = (question or "").strip()

        attempts = [
            ("You are a careful grade-school math solver.", self._solve_prompt(q)),
            ("You are a precise arithmetic calculator.", self._arithmetic_prompt(q)),
            ("You are a careful math checker.", self._check_prompt(q)),
        ]

        answers = []
        for system, prompt in attempts:
            resp = self._safe_llm(prompt, system=system, temperature=0.0)
            ans = self._extract_answer(resp)
            if ans is not None:
                answers.append(ans)

        if not answers:
            resp = self._safe_llm(self._final_only_prompt(q), system="", temperature=0.0)
            ans = self._extract_answer(resp)
            return ans if ans is not None else "0"

        if len(answers) == 1:
            return answers[0]

        winner, count = self._most_common(answers)
        if count >= 2:
            return winner

        unique = list(dict.fromkeys(answers))
        resp = self._safe_llm(
            self._verify_prompt(q, unique),
            system="You are a careful answer checker.",
            temperature=0.0,
        )
        verified = self._extract_answer(resp)
        if verified is not None:
            return verified

        return answers[0]

    def _solve_prompt(self, q: str) -> str:
        return (
            "Solve the grade-school math problem step by step. "
            "Put the final numeric answer on its own line exactly like: #### 42\n\n"
            f"Question: {q}\n\nAnswer:"
        )

    def _arithmetic_prompt(self, q: str) -> str:
        return (
            "Compute the final numeric answer for the problem. "
            "Show only the necessary arithmetic, do not include units, and end with a line exactly like: #### <number>\n\n"
            f"Question: {q}\n\nAnswer:"
        )

    def _check_prompt(self, q: str) -> str:
        return (
            "Solve the problem, then check the result by reversing the calculation or estimating. "
            "If the check fails, correct the answer. End with the final numeric answer on a line exactly like: #### <number>\n\n"
            f"Question: {q}\n\nChecked answer:"
        )

    def _final_only_prompt(self, q: str) -> str:
        return (
            "Give only the final numeric answer for the problem, with no units and no explanation. "
            "End with a line exactly like: #### <number>\n\n"
            f"Question: {q}\n\n####"
        )

    def _verify_prompt(self, q: str, candidates) -> str:
        cand = ", ".join(candidates)
        return (
            f"Several attempts gave these candidate numeric answers: {cand}.\n"
            "Determine the correct answer for the problem. You may solve it again if needed.\n"
            "End with a line exactly like: #### <number>\n\n"
            f"Question: {q}\n\nFinal answer:"
        )

    def _safe_llm(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""

        if out is None:
            return ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "ignore")
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or out.get("completion") or ""

        return str(out)

    def _extract_answer(self, text: str):
        if not text:
            return None

        text = str(text)
        text = text.replace("\u2212", "-").replace("\u00a0", " ")

        explicit = []
        for pattern in self._STRONG_ANSWER_PATTERNS:
            for m in pattern.finditer(text):
                norm = self._normalize_number(m.group(1))
                if norm is not None:
                    explicit.append((m.end(), norm))

        if explicit:
            explicit.sort(key=lambda item: item[0])
            return explicit[-1][1]

        for pattern in self._WEAK_ANSWER_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                for match in reversed(matches):
                    norm = self._normalize_number(match)
                    if norm is not None:
                        return norm

        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        for line in reversed(lines[-8:]):
            nums = self._NUM_RE.findall(line)
            if nums:
                norm = self._normalize_number(nums[-1])
                if norm is not None:
                    return norm

        nums = self._NUM_RE.findall(text)
        if nums:
            return self._normalize_number(nums[-1])

        return None

    def _normalize_number(self, raw):
        if raw is None:
            return None

        raw_str = str(raw).strip()
        m = self._NUM_RE.search(raw_str)
        if not m:
            return None

        s = m.group(0).replace(",", "").strip()
        if raw_str.startswith("-") and not s.startswith("-"):
            s = "-" + s
        if s.startswith("+"):
            s = s[1:]

        if not s or s == "-":
            return None

        try:
            if "." in s:
                whole, frac = s.split(".", 1)
                frac = frac.rstrip("0")

                sign = ""
                if whole.startswith("-"):
                    sign = "-"
                    whole = whole[1:]
                elif whole.startswith("+"):
                    whole = whole[1:]

                whole = whole.lstrip("0") or "0"

                if frac == "":
                    if whole == "0":
                        return "0"
                    return sign + whole

                return f"{sign}{whole}.{frac}"

            return str(int(s))
        except Exception:
            return None

    def _most_common(self, items):
        counts = {}
        order = []

        for item in items:
            if item not in counts:
                counts[item] = 0
                order.append(item)
            counts[item] += 1

        best = None
        best_count = 0
        for item in order:
            if counts[item] > best_count:
                best = item
                best_count = counts[item]

        return best, best_count