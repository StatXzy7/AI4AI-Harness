"""Break a natural-language question into ordered sub-questions, generate SQL for each, and assemble them into a final SQL query."""
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # Step 1: Decompose the question into ordered sub-questions.
        subquestions = self._decompose_question(question, schema)

        # Fallback: if decomposition fails, generate a direct SQL query.
        if not subquestions:
            return self._generate_direct_sql(question, schema)

        decomp_text = "\n".join(
            f"{i + 1}. {sq}" for i, sq in enumerate(subquestions)
        )

        cte_defs = []
        previous_ctes = []

        # Step 2: Generate a SQL query for each sub-question, in order.
        for idx, subq in enumerate(subquestions, start=1):
            cte_name = f"q{idx}"

            prompt = self._subquestion_sql_prompt(
                schema,
                question,
                decomp_text,
                previous_ctes,
                subq,
                cte_name,
            )

            raw_sql = self._llm_text(prompt)
            sql = bridge.extract_sql(raw_sql)

            if not sql:
                sql = f"SELECT NULL AS {cte_name}_placeholder"

            sql = self._clean_sql(sql)

            # Execute best-effort to enrich subsequent context with status.
            exec_result = self._execute_safe(sql)
            if exec_result.get("ok"):
                rows = exec_result.get("rows", [])
                status = f"execution succeeded: {len(rows)} rows returned"
            else:
                status = f"execution failed: {exec_result.get('error', 'unknown error')}"

            cte_defs.append(f"{cte_name} AS (\n{sql}\n)")
            previous_ctes.append(f"{cte_name} ({status}):\n{sql}")

        # Step 3: Assemble final SQL from the generated CTEs.
        cte_block = ",\n".join(cte_defs)
        final_prompt = self._assembly_prompt(
            schema,
            question,
            decomp_text,
            cte_block,
        )

        raw_final = self._llm_text(final_prompt)
        final_sql = bridge.extract_sql(raw_final)

        if not final_sql:
            # Fallback: use the last generated sub-query as final SQL.
            final_sql = cte_defs[-1].split(" AS (\n", 1)[-1].rsplit("\n)", 1)[0]

        return self._clean_sql(final_sql)

    def _decompose_question(self, question: str, schema: str):
        prompt = (
            "You are an expert SQL planner. Given a database schema and a complex "
            "natural language question, break the question into a minimal ordered "
            "list of sub-questions. Each sub-question should be answerable by a "
            "single SELECT query against the schema and should contribute toward "
            "the final SQL answer. Order the sub-questions from base data retrieval "
            "to final computation.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            'Return ONLY a JSON list of strings, for example: ["sub-question 1", '
            '"sub-question 2"]. No explanation.'
        )
        raw = self._llm_text(prompt)
        return self._parse_json_list(raw)

    def _generate_direct_sql(self, question: str, schema: str) -> str:
        prompt = (
            "You are an expert SQL query generator. Given a database schema and a "
            "natural language question, write a single SQL query that answers the "
            "question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return ONLY SQL, without markdown fences or explanation."
        )
        raw = self._llm_text(prompt)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = "SELECT NULL AS placeholder"
        return self._clean_sql(sql)

    def _subquestion_sql_prompt(
        self,
        schema: str,
        question: str,
        decomp_text: str,
        previous_ctes,
        subquestion: str,
        cte_name: str,
    ) -> str:
        if previous_ctes:
            previous_block = "\n\n".join(previous_ctes)
        else:
            previous_block = "(none)"

        return (
            "You are an expert SQL query generator.\n\n"
            f"Database schema:\n{schema}\n\n"
            f"Original question:\n{question}\n\n"
            f"Ordered decomposition:\n{decomp_text}\n\n"
            f"Previously generated CTE definitions and status:\n{previous_block}\n\n"
            f"Current sub-question to answer:\n{subquestion}\n\n"
            f"Write a single SELECT query that answers only this current sub-question. "
            f"It will be used as a CTE named `{cte_name}`. Ensure all referenced "
            "tables/columns exist in the schema. Return ONLY SQL, without markdown "
            "fences or explanation."
        )

    def _assembly_prompt(
        self,
        schema: str,
        question: str,
        decomp_text: str,
        cte_block: str,
    ) -> str:
        return (
            "You are an expert SQL query writer.\n\n"
            f"Database schema:\n{schema}\n\n"
            f"Original question:\n{question}\n\n"
            f"Ordered decomposition:\n{decomp_text}\n\n"
            f"Intermediate CTEs already generated:\n{cte_block}\n\n"
            "Write a final SQL query that answers the original question. "
            "Use the provided CTE definitions in a WITH clause where appropriate. "
            "Return ONLY SQL, without markdown fences or explanation."
        )

    def _parse_json_list(self, text: str):
        if not text:
            return []

        data = None
        try:
            data = json.loads(text)
        except Exception:
            pass

        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]

        if isinstance(data, dict):
            for key in ("subquestions", "sub_questions", "questions", "decomposition"):
                if key in data and isinstance(data[key], list):
                    return [str(item).strip() for item in data[key] if str(item).strip()]

        # Try to extract a JSON list from inside markdown or surrounding text.
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return [str(item).strip() for item in data if str(item).strip()]
            except Exception:
                pass

        # Fallback: treat non-empty lines as sub-questions.
        subquestions = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or line in ("[", "]"):
                continue
            line = re.sub(r"^\d+[.)]\s*", "", line)
            line = re.sub(r"^[-*]\s*", "", line)
            line = line.strip().strip('"').strip("'").rstrip(",")
            if line:
                subquestions.append(line)

        # Cap to avoid overly large prompts.
        return subquestions[:8]

    def _llm_text(self, prompt: str, system: str = "") -> str:
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(result, dict):
            return str(result.get("text") or result.get("content") or "")
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else ""
        return str(result)

    def _execute_safe(self, sql: str):
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    @staticmethod
    def _clean_sql(sql: str) -> str:
        sql = sql.strip()
        if sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql