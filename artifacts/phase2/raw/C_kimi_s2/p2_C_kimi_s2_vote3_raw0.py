"""Self-consistency harness: sample 3 independent SQL attempts from the frozen solver (n=3, temperature=0.7), execute every attempt that parses, and return the SQL whose execution result wins the majority vote."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Vote3(SQLHarness):
    """Three-sample execution-based majority-vote (self-consistency) Text-to-SQL harness."""

    N_SAMPLES = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, write a single syntactically valid SQL query "
        "that answers the question. Output only the SQL query."
    )

    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Write the SQL query that answers the question. Output only SQL."
        )

    @staticmethod
    def _canonicalize_rows(rows) -> str:
        """Order-insensitive, hashable fingerprint of an execution result."""
        try:
            return repr(sorted(repr(row) for row in rows))
        except Exception:
            return repr(rows)

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # Step 1: ask the frozen solver for 3 independent attempts at temperature 0.7.
        response = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            n=self.N_SAMPLES,
        )
        if isinstance(response, str):
            completions = [response]
        else:
            completions = list(response)

        # Step 2: extract SQL from each completion and execute all that parse.
        extracted = []
        candidates = []  # [{"sql": ..., "key": <result fingerprint>}]
        for text in completions:
            sql = bridge.extract_sql(text)
            if not sql:
                continue
            extracted.append(sql)
            try:
                outcome = self.execute(sql)
            except Exception:
                continue
            if not outcome.get("ok"):
                continue
            key = self._canonicalize_rows(outcome.get("rows", []))
            candidates.append({"sql": sql, "key": key})

        # Step 3: majority vote over execution results (ties -> earliest group).
        if candidates:
            groups = {}
            order = []
            for cand in candidates:
                key = cand["key"]
                if key not in groups:
                    groups[key] = {"count": 0, "sql": cand["sql"]}
                    order.append(key)
                groups[key]["count"] += 1
            best_key = max(order, key=lambda k: groups[k]["count"])
            return groups[best_key]["sql"]

        # Fallbacks: nothing executed successfully.
        if extracted:
            return extracted[0]
        if completions:
            sql = bridge.extract_sql(completions[0])
            return sql if sql else completions[0]
        return "SELECT 1"