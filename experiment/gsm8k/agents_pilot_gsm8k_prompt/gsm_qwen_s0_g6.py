"""Improves greedy decoding with adaptive majority-vote self-consistency across diverse prompts and weighted answer extraction."""

from ..harness_base import MathHarness

import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation


class GsmGsmQwenS0G6(MathHarness):
    _NUMBER = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'

    _HASH_RE = re.compile(
        r'####\s*(?:\$|USD)?\s*(' + _NUMBER + r')',
        re.I,
    )

    _ANSWER_RE = re.compile(
        r'(?:final answer|answer|the answer|result|total)\s*(?:is|:|=)?\s*(?:\$|USD)?\s*('
        + _NUMBER
        + r')',
        re.I,
    )

    _NUM_RE = re.compile(_NUMBER)

    _SYSTEM = (
        "You are a careful grade-school math solver. "
        "End your response with the final numeric answer after ####."
    )

    def solve(self, question: str) -> str:
        q = (question or "").strip()
        candidates = []

        # First round: cheap diverse attempts.
        first_round = [
            (self._prompt_direct(q), 0.0),
            (self._prompt_step_by_step(q), 0.0),
            (self._prompt_check_arithmetic(q), 0.2),
        ]

        for prompt, temperature in first_round:
            self._add_candidate(q, prompt, temperature, candidates)

        winner = self._unique_majority(candidates)
        if winner is not None:
            return winner

        # Second round: only used if the first round lacks a clear majority.
        second_round = [
            (self._prompt_quantities(q), 0.2),
            (self._prompt_concise(q), 0.0),
        ]

        for prompt, temperature in second_round:
            self._add_candidate(q, prompt, temperature, candidates)

        winner = self._unique_majority(candidates)
        if winner is not None:
            return winner

        return self._weighted_choice(candidates)

    def _add_candidate(self, question: str, prompt: str, temperature: float, candidates: list) -> None:
        raw = self._safe_llm(prompt, self._SYSTEM, temperature)
        answer, score = self._extract_answer_with_score(raw)

        # If the solver produced text but no parseable answer, ask for extraction only.
        if answer is None and raw.strip():
            extraction_prompt = self._prompt_extract(raw)
            extraction_system = (
                "You extract the final numeric answer from a math solution. "
                "Output only the number."
            )
            raw2 = self._safe_llm(extraction_prompt, extraction_system, 0.0)
            answer, score2 = self._extract_answer_with_score(raw2)
            if answer is not None:
                score = max(0, score2 - 1)

        if answer is not None:
            candidates.append({"answer": answer, "score": score})

    def _unique_majority(self, candidates: list):
        if not candidates:
            return None

        counts = Counter(c["answer"] for c in candidates)
        if not counts:
            return None

        top_count = max(counts.values())
        if top_count < 2:
            return None

        top_answers = [answer for answer, count in counts.items() if count == top_count]
        if len(top_answers) == 1:
            return top_answers[0]

        return None

    def _weighted_choice(self, candidates: list) -> str:
        if not candidates:
            return "0"

        counts = Counter()
        scores = defaultdict(int)
        first_index = {}

        for i, cand in enumerate(candidates):
            answer = cand["answer"]
            counts[answer] += 1
            scores[answer] += cand.get("score", 1)
            if answer not in first_index:
                first_index[answer] = i

        return max(
            counts.keys(),
            key=lambda a: (counts[a], scores[a], -first_index[a]),
        )

    def _safe_llm(self, prompt: str, system: str, temperature: float) -> str:
        try:
            resp = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""

        if isinstance(resp, list):
            resp = resp[0] if resp else ""

        if isinstance(resp, dict):
            if "choices" in resp and isinstance(resp["choices"], list) and resp["choices"]:
                choice = resp["choices"][0]
                if isinstance(choice, dict):
                    message = choice.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        resp = message["content"]
                    elif isinstance(choice.get("text"), str):
                        resp = choice["text"]
                    else:
                        resp = str(choice)
                else:
                    resp = str(choice)
            else:
                for key in ("text", "completion", "output"):
                    if key in resp and isinstance(resp[key], str):
                        resp = resp[key]
                        break
                else:
                    resp = str(resp)

        if not isinstance(resp, str):
            resp = str(resp)

        return resp

    def _extract_answer_with_score(self, text: str):
        if not text or not text.strip():
            return None, 0

        # Strongest signal: explicit GSM-style final answer.
        matches = self._HASH_RE.findall(text)
        if matches:
            answer = self._canonical_number(matches[-1])
            if answer is not None:
                return answer, 4

        # Next strongest: natural-language final-answer phrase.
        matches = self._ANSWER_RE.findall(text)
        if matches:
            answer = self._canonical_number(matches[-1])
            if answer is not None:
                return answer, 3

        # Near-final line containing a number.
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        for line in reversed(lines[-10:]):
            nums = self._NUM_RE.findall(line)
            if nums and len(line) <= 120:
                answer = self._canonical_number(nums[-1])
                if answer is not None:
                    return answer, 2

        # Last-resort: last number anywhere in the response.
        nums = self._NUM_RE.findall(text)
        if nums:
            answer = self._canonical_number(nums[-1])
            if answer is not None:
                return answer, 1

        return None, 0

    def _canonical_number(self, token: str):
        if token is None:
            return None

        s = str(token).strip()
        s = s.replace(",", "").replace("$", "").replace("%", "").replace(" ", "")
        s = s.rstrip(".")

        if s.startswith("+"):
            s = s[1:]

        if not s:
            return None

        try:
            d = Decimal(s)
        except InvalidOperation:
            # Occasionally a model may emit a simple fraction.
            m = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)', s)
            if not m:
                return None
            try:
                num = Decimal(m.group(1))
                den = Decimal(m.group(2))
                if den == 0:
                    return None
                d = num / den
            except Exception:
                return None

        try:
            if d == d.to_integral_value():
                return str(int(d))
            return format(d.normalize(), "f")
        except Exception:
            return None

    def _prompt_direct(self, question: str) -> str:
        return (
            f"Problem: {question}\n\n"
            "Solve the problem. Show brief reasoning, then end with the final numeric "
            "answer after ####. Do not include units."
        )

    def _prompt_step_by_step(self, question: str) -> str:
        return (
            f"Problem: {question}\n\n"
            "Think step by step. Then give the final numeric answer after ####. "
            "Do not include units."
        )

    def _prompt_check_arithmetic(self, question: str) -> str:
        return (
            f"Problem: {question}\n\n"
            "Solve carefully. After solving, check each arithmetic operation. "
            "If anything is wrong, correct it. End with the final numeric answer "
            "after ####. Do not include units."
        )

    def _prompt_quantities(self, question: str) -> str:
        return (
            f"Problem: {question}\n\n"
            "First list the known quantities and what is being asked. "
            "Then compute the answer. End with the final numeric answer after ####. "
            "Do not include units."
        )

    def _prompt_concise(self, question: str) -> str:
        return (
            f"Problem: {question}\n\n"
            "Give the final numeric answer only, after ####. Do not include units."
        )

    def _prompt_extract(self, raw_solution: str) -> str:
        snippet = raw_solution[-1500:]
        return (
            "Below is a solution to a math problem. Extract only the final numeric answer. "
            "If there is a line containing ####, use the number after the last ####. "
            "Output only the number.\n\n"
            f"{snippet}"
        )