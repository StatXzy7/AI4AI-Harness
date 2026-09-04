"""Generates several SQL candidates and selects the final query by voting among executable candidates."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = str(getattr(self, "schema", "") or "")
        system = (
            "You are an expert Text-to-SQL system. "
            "Return only one executable SQL statement, with no markdown and no explanations."
        )

        prompts = [
            self._direct_prompt(question, schema),
            self._schema_grounded_prompt(question, schema),
            self._conservative_prompt(question, schema),
        ]

        candidates = []
        seen = set()

        for prompt in prompts:
            raw = self._llm_text(prompt, system, temperature=0.0)
            sql = self._extract_sql(raw, fallback="")
            if not sql:
                continue

            normalized = self._normalize(sql)
            if normalized in seen:
                continue

            seen.add(normalized)
            candidates.append({"sql": sql})

        if not candidates:
            raw = self._llm_text(self._direct_prompt(question, schema), system, temperature=0.0)
            return self._extract_sql(raw, fallback="SELECT 1")

        for candidate in candidates:
            result = self._safe_execute(candidate["sql"])
            candidate["ok"] = bool(result.get("ok"))
            candidate["error"] = str(result.get("error") or "")
            rows = result.get("rows")
            candidate["row_count"] = len(rows) if isinstance(rows, list) else 0

        executable = [candidate for candidate in candidates if candidate["ok"]]

        if len(executable) == 1:
            return executable[0]["sql"]

        if len(executable) > 1:
            chosen = self._choose_by_judge(question, schema, executable)
            return chosen["sql"] if chosen else executable[0]["sql"]

        chosen = self._choose_by_judge(question, schema, candidates)
        return chosen["sql"] if chosen else candidates[0]["sql"]

    def _direct_prompt(self, question: str, schema: str) -> str:
        return (
            "Write a single SQL query that answers the question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

    def _schema_grounded_prompt(self, question: str, schema: str) -> str:
        return (
            "Using only the tables and columns shown in the schema, write a single SQL query "
            "that answers the question. Do not invent columns.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

    def _conservative_prompt(self, question: str, schema: str) -> str:
        return (
            "Produce the simplest executable SQL query that answers the question. "
            "Prefer explicit joins and standard SQLite syntax.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

    def _choose_by_judge(self, question: str, schema: str, candidates):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        lines = []
        for index, candidate in enumerate(candidates, start=1):
            lines.append(f"{index}. {candidate['sql']}")

        prompt = (
            "Choose the SQL query that best answers the question.\n"
            "Reply with only the number of the chosen query.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Candidates:\n" + "\n".join(lines)
        )

        raw = self._llm_text(
            prompt,
            "You are an exact SQL evaluator. Reply with only a number.",
            temperature=0.0,
        )
        number = self._parse_number(raw)

        if number is not None and 1 <= number <= len(candidates):
            return candidates[number - 1]

        return None

    def _parse_number(self, text: str):
        text = str(text or "").strip()
        digits = []

        for character in text:
            if character.isdigit():
                digits.append(character)
            elif digits:
                break

        if not digits:
            return None

        try:
            return int("".join(digits))
        except Exception:
            return None

    def _llm_text(self, prompt: str, system: str, temperature: float = 0.0) -> str:
        try:
            output = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        return self._coerce_text(output)

    def _coerce_text(self, output) -> str:
        if output is None:
            return ""

        if isinstance(output, (list, tuple)):
            for item in output:
                text = self._coerce_text(item)
                if text:
                    return text
            return ""

        if isinstance(output, dict):
            choices = output.get("choices")
            if isinstance(choices, list) and choices:
                text = self._coerce_text(choices[0])
                if text:
                    return text

            message = output.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content

            for key in ("text", "completion", "content", "output"):
                if key in output:
                    text = self._coerce_text(output[key])
                    if text:
                        return text

            return ""

        return str(output)

    def _extract_sql(self, text: str, fallback: str) -> str:
        text = str(text or "")

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        sql = str(sql or "").strip().rstrip(";").strip()
        if sql:
            return sql

        cleaned = text.strip()
        if cleaned:
            lowered = cleaned.lower()
            if lowered.startswith(("select", "with", "pragma", "explain")):
                return cleaned.rstrip(";").strip()

        return fallback

    def _normalize(self, sql: str) -> str:
        return " ".join(str(sql or "").strip().lower().split())

    def _safe_execute(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"ok": bool(result), "rows": [], "error": ""}