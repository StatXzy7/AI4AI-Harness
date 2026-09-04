"""Harness that parses the Hint line and restates its constraints as hard requirements before writing SQL."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hint = self._extract_hint(question)
        hard_requirements = self._build_hard_requirements(hint)
        sql = self._generate_sql(question, hint, hard_requirements)
        sql = self._validate_and_repair(question, hint, hard_requirements, sql)
        return str(sql or "SELECT 1")

    def _schema_text(self) -> str:
        try:
            return str(getattr(self, "schema", "") or "")
        except Exception:
            return ""

    def _extract_hint(self, question: str) -> str:
        text = str(question or "")
        lines = text.splitlines()

        inline = re.compile(r"^\s*(?:[-*]\s*)?hint\s*[:\-]\s*(?P<hint>.+)$", re.I)
        bare = re.compile(r"^\s*(?:[-*]\s*)?hint\s*[:\-]?\s*$", re.I)

        for i, line in enumerate(lines):
            m = inline.match(line)
            if m:
                return m.group("hint").strip()

            if bare.match(line):
                for nxt in lines[i + 1:]:
                    if nxt.strip():
                        return nxt.strip()

        m = re.search(r"\bhint\s*[:\-]\s*(?P<hint>[^\n]+)", text, re.I)
        return m.group("hint").strip() if m else ""

    def _build_hard_requirements(self, hint: str) -> str:
        hint = (hint or "").strip()
        if not hint:
            return ""

        chunks = re.split(r";|\n|\s+and then\s+|\s+then\s+|\s+also\s+", hint, flags=re.I)
        requirements = []

        starter = re.compile(
            r"^(?:must|ensure|use|only|filter|include|exclude|join|group|order|limit|select|return|count|sum|avg|min|max|calculate|compute|apply|consider|treat|match|require|required)\b",
            re.I,
        )

        for chunk in chunks:
            chunk = chunk.strip().strip(".! ").strip()
            chunk = re.sub(r"^(?:[-*]|\d+[.)])\s*", "", chunk)
            if not chunk:
                continue

            if not starter.match(chunk):
                if len(chunk) > 1:
                    chunk = f"Ensure {chunk[0].lower()}{chunk[1:]}"
                else:
                    chunk = f"Ensure {chunk}"

            requirements.append(f"- HARD REQUIREMENT: {chunk}")

        if not requirements:
            requirements.append(f"- HARD REQUIREMENT: {hint}")

        return "\n".join(requirements)

    def _generate_sql(self, question: str, hint: str, hard_requirements: str) -> str:
        prompt = f"""Write one SQL statement to answer the question.
Return ONLY the SQL statement, without explanation or markdown.

Schema:
{self._schema_text()}

Question:
{question}

Hint:
{hint or "None"}

Hard requirements extracted from the hint (mandatory; override conflicting guidance):
{hard_requirements or "None"}

SQL:"""

        raw = self._llm_text(
            prompt,
            system="You are a precise Text-to-SQL engine. Output only SQL.",
        )
        return self._extract_sql(raw)

    def _validate_and_repair(self, question: str, hint: str, hard_requirements: str, sql: str) -> str:
        candidate = (sql or "").strip()
        last_error = ""

        for _ in range(3):
            if not candidate:
                break

            ok, error = self._execute_sql(candidate)
            if ok:
                return candidate

            last_error = error
            prompt = f"""The following SQL failed. Fix it so it answers the question and satisfies the hard requirements.
Return ONLY the corrected SQL statement, without explanation or markdown.

Schema:
{self._schema_text()}

Question:
{question}

Hint:
{hint or "None"}

Hard requirements:
{hard_requirements or "None"}

Previous SQL:
{candidate}

Error:
{last_error}

SQL:"""

            raw = self._llm_text(
                prompt,
                system="You are a precise Text-to-SQL repair engine. Output only SQL.",
            )
            repaired = self._extract_sql(raw)

            if not repaired or repaired.strip() == candidate:
                break

            candidate = repaired

        return candidate

    def _execute_sql(self, sql: str):
        if not sql or not str(sql).strip():
            return False, "empty SQL"

        try:
            result = self.execute(str(sql))
        except Exception as exc:
            return False, str(exc)

        if isinstance(result, dict):
            if result.get("ok"):
                return True, ""
            return False, result.get("error") or "execution failed"

        return True, ""

    def _llm_text(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(response, list):
            response = response[0] if response else ""

        if isinstance(response, dict):
            if "choices" in response and isinstance(response["choices"], list):
                response = response["choices"][0] if response["choices"] else ""

            if isinstance(response, dict):
                if "text" in response:
                    response = response["text"]
                elif "completion" in response:
                    response = response["completion"]
                elif "content" in response:
                    response = response["content"]
                elif "message" in response and isinstance(response["message"], dict):
                    response = response["message"].get("content", "")
                elif "sql" in response:
                    response = response["sql"]
                else:
                    response = str(response)

        return str(response).strip()

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
            if extracted and str(extracted).strip():
                return str(extracted).strip().rstrip(";").strip()
        except Exception:
            pass

        cleaned = str(text).strip()

        if cleaned.startswith("