"""Parses the Hint line from a question, restates it as explicit hard requirements for SQL generation, and enforces them through execution-guided correction before returning SQL."""

from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2CDeepseekS1HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hint, clean_question = self._extract_hint(question)
        hard_requirements = self._format_hard_requirements(hint)
        has_hint = bool(hint)
        system = self._build_system(hard_requirements)
        prompt = self._build_initial_prompt(clean_question, hard_requirements)

        last_sql = ""
        last_ok_sql = ""
        max_attempts = 3

        for _ in range(max_attempts):
            output = self._call_llm(prompt, system=system)
            candidate_sql = self._extract_sql(output)
            last_sql = candidate_sql

            if not candidate_sql:
                prompt = self._build_correction_prompt(
                    clean_question, hard_requirements, "No SQL was generated."
                )
                continue

            exec_result = self.execute(candidate_sql)
            if not exec_result.get("ok"):
                error = exec_result.get("error", "Unknown execution error")
                prompt = self._build_correction_prompt(
                    clean_question,
                    hard_requirements,
                    f"Execution error: {error}",
                    candidate_sql,
                )
                continue

            last_ok_sql = candidate_sql
            if not has_hint:
                return candidate_sql

            check_prompt = self._build_hint_check_prompt(
                candidate_sql, clean_question, hard_requirements
            )
            check_output = self._call_llm(check_prompt, system=system)
            if self._parse_verdict(check_output):
                return candidate_sql

            prompt = self._build_correction_prompt(
                clean_question,
                hard_requirements,
                f"Hint requirement likely violated: {check_output}",
                candidate_sql,
            )

        return last_ok_sql or last_sql or ""

    def _extract_hint(self, question: str):
        hint_parts = []
        clean_lines = []
        found = False
        for line in question.splitlines():
            m = re.match(r'^\s*hint\s*:\s*(.*)$', line, re.IGNORECASE)
            if m:
                hint_parts.append(m.group(1).strip())
                found = True
            else:
                clean_lines.append(line)

        if found:
            hint = " ".join(p for p in hint_parts if p)
            clean_question = "\n".join(clean_lines).strip()
            return hint, clean_question

        m = re.search(r'\bHint\s*:\s*(.*?)(?:\n|$)', question, re.IGNORECASE)
        if m:
            hint = m.group(1).strip()
            clean_question = question[:m.start()] + question[m.end():]
            return hint, clean_question.strip()

        return "", question

    def _format_hard_requirements(self, hint: str) -> str:
        if not hint:
            return ""
        return (
            "HARD REQUIREMENTS (from the question's Hint line; these are mandatory and "
            "must all be satisfied by your SQL):\n"
            f"- {hint}\n"
            "Do not ignore or weaken any part of this hint."
        )

    def _build_system(self, hard_requirements: str) -> str:
        system = "You are a senior SQL developer. Write only the final SQL query, no explanation."
        if hard_requirements:
            system += "\n\n" + hard_requirements
        return system

    def _build_initial_prompt(self, clean_question: str, hard_requirements: str) -> str:
        prompt = f"Database schema:\n{self.schema}\n\nQuestion:\n{clean_question}\n"
        if hard_requirements:
            prompt += f"\n{hard_requirements}\n"
        prompt += "\nWrite a SQL query that answers the question and satisfies all hard requirements. Return only SQL."
        return prompt

    def _build_correction_prompt(
        self,
        clean_question: str,
        hard_requirements: str,
        feedback: str,
        previous_sql: str = "",
    ) -> str:
        prompt = f"Database schema:\n{self.schema}\n\nQuestion:\n{clean_question}\n"
        if hard_requirements:
            prompt += f"\n{hard_requirements}\n"
        if previous_sql:
            prompt += f"\nPrevious SQL:\n{previous_sql}\n"
        prompt += f"\nFeedback:\n{feedback}\n"
        prompt += "\nWrite a corrected SQL query that answers the question and satisfies all hard requirements. Return only SQL."
        return prompt

    def _build_hint_check_prompt(
        self, candidate_sql: str, clean_question: str, hard_requirements: str
    ) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{clean_question}\n\n"
            f"{hard_requirements}\n\n"
            f"Generated SQL:\n{candidate_sql}\n\n"
            "Does the generated SQL satisfy all hard requirements? Answer YES or NO. If NO, explain what is wrong and provide a corrected SQL query."
        )
        return prompt

    def _parse_verdict(self, text: str) -> bool:
        m = re.search(r'\b(yes|no)\b', text, re.IGNORECASE)
        if m:
            return m.group(1).lower() == "yes"
        return False

    def _call_llm(self, prompt: str, system: str = "") -> str:
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(result, list):
            if not result:
                return ""
            result = result[0]
        if isinstance(result, dict):
            return str(result.get("text") or result.get("message") or "")
        return str(result).strip()

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""
        sql = bridge.extract_sql(text)
        if isinstance(sql, list):
            sql = " ".join(sql)
        if sql and isinstance(sql, str):
            return sql.strip()

        fallback = text.strip()
        if fallback.startswith("