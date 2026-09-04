A text-to-SQL harness that generates an explicit plan, samples multiple SQL candidates, validates them by execution, and repairs failures iteratively.
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        plan = self._generate_plan(question)
        candidates = self._generate_candidates(question, plan)

        if not candidates:
            # Last-resort direct generation without a plan.
            candidates = self._generate_candidates(question, "", direct=True)
        if not candidates:
            candidates = ["SELECT 1"]

        candidate_results = []
        successful = []

        for sql in candidates:
            res = self.execute(sql)
            candidate_results.append((sql, res))
            if res.get("ok"):
                successful.append((sql, res))

        # Repair loop: use execution errors to revise failed candidates.
        attempts = 0
        while not successful and attempts < 2:
            new_candidates = []
            known_sqls = {sql for sql, _ in candidate_results}

            for sql, res in candidate_results:
                if res.get("ok"):
                    continue
                error = res.get("error") or "Unknown execution error"
                repaired_sql = self._repair_sql(question, plan, sql, error)
                if repaired_sql and repaired_sql not in known_sqls and repaired_sql not in new_candidates:
                    new_candidates.append(repaired_sql)

            if not new_candidates:
                break

            for sql in new_candidates:
                res = self.execute(sql)
                candidate_results.append((sql, res))
                if res.get("ok"):
                    successful.append((sql, res))

            attempts += 1

        if successful:
            if len(successful) == 1:
                return successful[0][0]
            return self._select_best(question, plan, successful)

        # Fallback: return the first candidate even if it did not execute.
        if candidate_results:
            return candidate_results[0][0]
        return "SELECT 1"

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    @staticmethod
    def _as_str(response):
        """Normalize an LLM response to a single string."""
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, (list, tuple)):
            return str(response[0]) if response else ""
        if hasattr(response, "text"):
            return str(response.text)
        return str(response)

    @staticmethod
    def _as_list(response):
        """Normalize an LLM response to a list of strings."""
        if response is None:
            return []
        if isinstance(response, str):
            return [response]
        if isinstance(response, (list, tuple)):
            return [str(x) for x in response]
        if hasattr(response, "text"):
            return [str(response.text)]
        return [str(response)]

    def _generate_plan(self, question: str) -> str:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a short step-by-step plan for constructing a SQLite SELECT query "
            "that answers the question. Do not write the SQL itself yet."
        )
        response = self.llm(prompt, system="You are a meticulous SQL planner.", temperature=0.0, n=1)
        return self._as_str(response)

    def _generate_candidates(self, question: str, plan: str, direct: bool = False) -> list[str]:
        if direct:
            prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Generate one SQLite SELECT query that answers the question. Output only SQL."
            )
        else:
            prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Plan:\n{plan}\n\n"
                "Generate one SQLite SELECT query that answers the question. Output only SQL."
            )

        response = self.llm(
            prompt,
            system="You are a text-to-SQL assistant.",
            temperature=0.2,
            n=3,
        )

        candidates = []
        for text in self._as_list(response):
            sql = bridge.extract_sql(text)
            if sql:
                candidates.append(sql)

        # Remove duplicates while preserving order.
        return list(dict.fromkeys(candidates))

    def _repair_sql(self, question: str, plan: str, previous_sql: str, error: str) -> str:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Write a corrected SQLite SELECT query. Output only SQL."
        )
        response = self.llm(
            prompt,
            system="You are a SQL expert fixing invalid queries.",
            temperature=0.0,
            n=1,
        )
        text = self._as_str(response)
        return bridge.extract_sql(text)

    def _select_best(self, question: str, plan: str, successful: list[tuple[str, dict]]) -> str:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            "Candidate SQL queries and their execution outcomes:\n"
        )
        for idx, (sql, res) in enumerate(successful, 1):
            rows = res.get("rows", [])
            preview = rows[:3]
            prompt += (
                f"\nCandidate {idx}:\n"
                f"SQL: {sql}\n"
                f"Row count: {len(rows)}\n"
                f"Rows preview: {preview}\n"
            )
        prompt += "\nChoose the single best SQL query. Output only that SQL."

        response = self.llm(
            prompt,
            system="You are an expert SQL evaluator.",
            temperature=0.0,
            n=1,
        )
        text = self._as_str(response)
        selected_sql = bridge.extract_sql(text)
        if selected_sql:
            return selected_sql

        # Fallback to the first successful candidate.
        return successful[0][0]