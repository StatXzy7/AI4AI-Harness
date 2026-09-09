"""Improves over one greedy call by generating two independent solutions, extracting numeric candidates, and resolving disagreements with a majority vote and a verifier call."""
import re
from collections import Counter

try:
    from ..harness_base import MathHarness
except ImportError:
    class MathHarness:
        def llm(self, prompt, system="", temperature=0.0, n=1):
            raise NotImplementedError("LLM backend must be provided.")


class GsmGsmQwenS0G0(MathHarness):
    _NUM_STRICT = r'[+-]?\d[\d,]*(?:\.\d+)?'
    _NUM_LENIENT = r'[+-]?\s*\d[\d,]*(?:\.\d+)?'

    _NUMBER_RE = re.compile(_NUM_STRICT)
    _HASH_RE = re.compile(rf'####\D*?({_NUM_LENIENT})', re.IGNORECASE)
    _PHRASE_RE = re.compile(
        rf'(?:final answer|answer is|answer:|the answer|therefore|result is|result:|total is|total:)\D*?({_NUM_LENIENT})',
        re.IGNORECASE,
    )

    def solve(self, question: str) -> str:
        q = str(question or "").strip()
        answers = []
        transcripts = []

        first_system = "You are a careful grade-school math tutor. Finish with #### <number>."
        second_system = "You are an independent grade-school math solver. Finish with #### <number>."

        for system, prompt in (
            (first_system, self._initial_prompt(q)),
            (second_system, self._second_prompt(q)),
        ):
            output = self._call(prompt, system=system, temperature=0.0)
            transcripts.append(output)
            answer = self._extract_answer(output)
            if answer is not None:
                answers.append(answer)

            if len(answers) >= 2 and answers[-1] == answers[-2]:
                return answers[-1]

        if len(answers) == 1:
            return answers[0]

        verifier_output = self._call(
            self._verifier_prompt(q, answers, transcripts),
            system="You are a meticulous math checker. Finish with #### <number>.",
            temperature=0.0,
        )
        transcripts.append(verifier_output)
        verifier_answer = self._extract_answer(verifier_output)

        if verifier_answer is not None:
            answers.append(verifier_answer)
            majority = self._majority(answers, min_count=2)
            if majority is not None:
                return majority
            return verifier_answer

        rescue_output = self._call(
            self._rescue_prompt(q, transcripts),
            system="You extract or compute the final numeric answer. Finish with #### <number>.",
            temperature=0.0,
        )
        rescue_answer = self._extract_answer(rescue_output)
        if rescue_answer is not None:
            return rescue_answer

        if answers:
            return answers[0]
        return "0"

    def _initial_prompt(self, question: str) -> str:
        return (
            "Solve this grade-school math problem step by step. Show each arithmetic step clearly. "
            "End with a line exactly like: #### <number>\n\n"
            f"Problem:\n{question}"
        )

    def _second_prompt(self, question: str) -> str:
        return (
            "Solve this grade-school math problem independently and carefully. "
            "Identify the requested quantity, perform the arithmetic, and check units. "
            "End with a line exactly like: #### <number>\n\n"
            f"Problem:\n{question}"
        )

    def _verifier_prompt(self, question: str, answers: list, transcripts: list) -> str:
        unique = self._unique_answers(answers)
        if unique:
            candidate_block = "\n".join(f"{i}. {answer}" for i, answer in enumerate(unique, 1))
        else:
            candidate_block = "No final answer was extracted."

        transcript_parts = []
        for i, transcript in enumerate(transcripts, 1):
            transcript_parts.append(f"Solution {i}:\n{self._truncate(transcript)}")
        transcript_block = "\n\n".join(transcript_parts) if transcript_parts else "No solutions were provided."

        return (
            "You are checking grade-school math solutions.\n\n"
            f"Problem:\n{question}\n\n"
            f"Candidate final answers:\n{candidate_block}\n\n"
            f"{transcript_block}\n\n"
            "Check the arithmetic and choose the correct final numerical answer. "
            "If all candidates are wrong or missing, solve the problem yourself. "
            "End with a line exactly like: #### <number>"
        )

    def _rescue_prompt(self, question: str, transcripts: list) -> str:
        transcript_parts = []
        for i, transcript in enumerate(transcripts, 1):
            transcript_parts.append(f"Attempt {i}:\n{self._truncate(transcript, limit=500)}")
        transcript_block = "\n\n".join(transcript_parts) if transcript_parts else "No attempts were provided."

        return (
            "Previous attempts did not yield a parseable final numeric answer.\n"
            "Use the attempts if helpful, then produce the final numeric answer.\n\n"
            f"Problem:\n{question}\n\n"
            f"{transcript_block}\n\n"
            "Output only one line in this exact format:\n#### <number>"
        )

    def _call(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            try:
                response = self.llm(prompt, system=system, temperature=temperature)
            except TypeError:
                response = self.llm(prompt)

        if isinstance(response, bytes):
            response = response.decode("utf-8", errors="ignore")
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        if isinstance(response, dict):
            response = (
                response.get("text")
                or response.get("completion")
                or response.get("response")
                or next(iter(response.values()), "")
            )

        return str(response or "")

    def _extract_answer(self, text: str):
        text = str(text or "")
        if not text.strip():
            return None

        pattern_candidates = []

        for match in self._HASH_RE.finditer(text):
            normalized = self._normalize_number(match.group(1))
            if normalized is not None:
                pattern_candidates.append((match.start(1), 1, normalized))

        for match in self._PHRASE_RE.finditer(text):
            normalized = self._normalize_number(match.group(1))
            if normalized is not None:
                pattern_candidates.append((match.start(1), 0, normalized))

        if pattern_candidates:
            pattern_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return pattern_candidates[0][2]

        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        for line in reversed(lines[-3:]):
            matches = self._NUMBER_RE.findall(line)
            if matches:
                for match in reversed(matches):
                    normalized = self._normalize_number(match)
                    if normalized is not None:
                        return normalized

        matches = self._NUMBER_RE.findall(text)
        if matches:
            for match in reversed(matches):
                normalized = self._normalize_number(match)
                if normalized is not None:
                    return normalized

        return None

    def _normalize_number(self, value):
        if value is None:
            return None

        s = str(value).strip()
        s = s.replace("*", "").replace("_", "").replace("$", "").replace("%", "").replace(" ", "")
        s = s.strip("`").strip()
        if not s:
            return None

        s = s.replace(",", "")
        if s.startswith("+"):
            s = s[1:]

        match = re.search(r'[+-]?\d+(?:\.\d+)?', s)
        if not match:
            return None

        s = match.group(0)
        if s.startswith("+"):
            s = s[1:]

        if "." in s:
            s = s.rstrip("0").rstrip(".")

        if s == "-0":
            return "0"
        if not s or s == "-":
            return None

        if not re.fullmatch(r'-?\d+(?:\.\d+)?', s):
            return None

        if "." in s:
            sign = "-" if s.startswith("-") else ""
            body = s[1:] if sign else s
            int_part, frac_part = body.split(".", 1)
            int_part = int_part.lstrip("0") or "0"
            return f"{sign}{int_part}.{frac_part}"

        if s.startswith("-"):
            digits = s[1:].lstrip("0")
            return "-" + digits if digits else "0"

        digits = s.lstrip("0")
        return digits or "0"

    def _majority(self, answers: list, min_count: int = 1):
        if not answers:
            return None

        counts = Counter(answers)
        answer, count = counts.most_common(1)[0]
        if count >= min_count:
            return answer
        return None

    def _unique_answers(self, answers: list) -> list:
        seen = set()
        unique = []
        for answer in answers:
            if answer is not None and answer not in seen:
                seen.add(answer)
                unique.append(answer)
        return unique

    def _truncate(self, text: str, limit: int = 1200) -> str:
        text = str(text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n... [truncated]"