"""Decompose the question into ordered sub-questions, answer each with a small LLM call, and assemble the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge
import json
import re


class P2P2CQwenS0Decompose(SQLHarness):
    MAX_SUBQUESTIONS = 5
    MAX_REPAIRS = 2

    def solve(self, question: str) -> str:
        question = (question or "").strip()

        subquestions = self._decompose(question) or self._default_subquestions()
        total = min(len(subquestions), self.MAX_SUBQUESTIONS)

        answers = []
        for idx, subq in enumerate(subquestions[:total], 1):
            answers.append((subq, self._answer_subquestion(question, subq, idx, total)))

        candidates = self._sql_candidates(self._assemble(question, answers))
        direct_used = False
        if not candidates:
            candidates = self._sql_candidates(self._direct_sql(question))
            direct_used = True

        best_sql = candidates[0] if candidates else ""

        for sql in candidates:
            if self._exec_ok(sql):
                return sql

        repaired = self._repair_loop(question, best_sql, answers)
        if repaired:
            return repaired

        if not direct_used:
            direct_candidates = self._sql_candidates(self._direct_sql(question))
            if direct_candidates:
                if self._exec_ok(direct_candidates[0]):
                    return direct_candidates[0]
                repaired = self._repair_loop(question, direct_candidates[0], answers)
                if repaired:
                    return repaired
                return direct_candidates[0]

        return best_sql or "SELECT 1"

    def _llm_text(self, prompt: str, system: str = "") -> str:
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""

        if isinstance(out, dict):
            if isinstance(out.get("choices"), list) and out["choices"]:
                choice = out["choices"][0]
                if isinstance(choice, dict):
                    if isinstance(choice.get("text"), str):
                        out = choice["text"]
                    elif isinstance(choice.get("message"), dict):
                        out = choice["message"].get("content", "")
            else:
                for key in ("text", "completion", "content", "output", "result"):
                    if key in out:
                        out = out[key]
                        break

        if out is None:
            return ""
        return str(out).strip()

    def _clip(self, text: str, limit: int = 6000) -> str:
        text = str(text or "")
        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[truncated]"

    def _decompose(self, question: str):
        system = "You are a SQL planning assistant. Output only a JSON array of strings."
        prompt = (
            "Schema:\n" + self._clip(self.schema) + "\n\n"
            "Question: " + question + "\n\n"
            "Break this question into 3-5 ordered sub-questions for writing a SQL query. "
            "Each sub-question must be short and help produce SQL. "
            "Output only a JSON array of strings. Example: "
            "[\"Which tables are needed?\", \"Which filters apply?\", \"What should be selected?\"]"
        )
        raw = self._llm_text(prompt, system=system)
        return self._parse_string_list(raw)

    def _default_subquestions(self):
        return [
            "Which tables are needed?",
            "Which columns, joins, and filters are needed?",
            "What aggregation, ordering, or limit is needed?",
            "What exact SELECT statement answers the question?",
        ]

    def _parse_string_list(self, raw: str):
        if not raw:
            return []
        text = raw.strip()

        parsed = self._try_json_list(text)
        if parsed:
            return parsed

        fence = re.search(r"