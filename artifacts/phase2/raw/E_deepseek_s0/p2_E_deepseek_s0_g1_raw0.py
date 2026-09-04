from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    """
    Generates multiple candidate SQL queries, executes them, and then
    either refines the best candidates or repairs failures based on
    execution results. The final SQL is always produced by the final
    generation stage.
    """

    def solve(self, question: str) -> str:
        schema = self.schema

        # Stage 1: sample at least two distinct candidate SQL queries.
        candidates = self._sample_candidates(question, schema, target=2)

        # Make candidate ordering deterministic for later selection steps.
        candidates = sorted(candidates)

        # Stage 2: execute every candidate exactly once.
        executed = []
        for sql in candidates:
            result = self.execute(sql)
            executed.append({"sql": sql, "result": result})

        clean = [entry for entry in executed if entry["result"].get("ok")]
        faulty = [entry for entry in executed if not entry["result"].get("ok")]

        # Stage 3: branch on whether at least one candidate executed cleanly.
        if clean:
            final_sql = self._refine_from_clean(question, schema, clean, faulty)
        else:
            final_sql = self._repair_from_faulty(question, schema, faulty)

        return final_sql

    def _sample_candidates(self, question: str, schema: str, target: int):
        candidates = []
        attempts = 0
        max_attempts = 20
        temperatures = [0.2, 0.6, 0.9, 0.1, 0.5, 0.8, 0.3, 0.7, 1.0, 0.4]
        system = "You are a SQL expert. Produce a single SQL SELECT statement and nothing else."

        while len(candidates) < target and attempts < max_attempts:
            temperature = temperatures[attempts % len(temperatures)]
            prompt = (
                f"Schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                "Write a SQL query that answers the question. Output only the SQL query."
            )
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
            sql = self._as_sql(response)

            if sql and sql not in candidates:
                candidates.append(sql)

            attempts += 1

        return candidates

    def _refine_from_clean(self, question: str, schema: str, clean, faulty) -> str:
        # Sort by SQL text so the prompt and therefore the result do not
        # depend on the original order in which candidates were generated.
        clean = sorted(clean, key=lambda entry: entry["sql"])
        faulty = sorted(faulty, key=lambda entry: entry["sql"])

        observations = []
        for entry in clean:
            rows = entry["result"].get("rows") or []
            preview = str(rows)[:200]
            observations.append(
                f"Candidate SQL:\n{entry['sql']}\n"
                f"Execution: OK, {len(rows)} row(s).\n"
                f"Rows preview: {preview}"
            )

        for entry in faulty:
            error = entry["result"].get("error", "")
            observations.append(
                f"Candidate SQL:\n{entry['sql']}\n"
                f"Execution failed: {error}"
            )

        observations_text = "\n\n".join(observations)

        prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Below are candidate SQL queries and their execution observations.\n"
            f"{observations_text}\n\n"
            "Return the best SQL query for the question. Use the observations to "
            "select or improve a candidate. Output only the SQL query."
        )

        system = (
            "You are a SQL expert. Use the execution observations to choose or "
            "improve the best candidate. Output only SQL."
        )

        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        return self._as_sql(response)

    def _repair_from_faulty(self, question: str, schema: str, faulty) -> str:
        # Sort by SQL text for deterministic repair order.
        faulty = sorted(faulty, key=lambda entry: entry["sql"])

        repaired = []
        system = (
            "You are a SQL expert. Fix the invalid SQL so that it executes cleanly. "
            "Output only SQL."
        )

        for entry in faulty:
            error = entry["result"].get("error", "")
            prompt = (
                f"Schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                "The following SQL query was invalid.\n"
                f"Invalid SQL:\n{entry['sql']}\n"
                f"Error:\n{error}\n\n"
                "Write a corrected SQL query. Output only the SQL query."
            )
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = self._as_sql(response)

            if sql and sql not in repaired:
                repaired.append(sql)

        # Defensive fallback: if every individual repair failed to produce a
        # usable SQL string, make one combined repair attempt.
        if not repaired:
            if faulty:
                failures = "\n\n".join(
                    f"Invalid SQL:\n{entry['sql']}\nError:\n{entry['result'].get('error', '')}"
                    for entry in faulty
                )
                prompt = (
                    f"Schema:\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    "The following candidate SQL queries all failed to execute:\n"
                    f"{failures}\n\n"
                    "Write a corrected SQL query. Output only the SQL query."
                )
            else:
                prompt = (
                    f"Schema:\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    "Write a SQL query that answers the question. Output only the SQL query."
                )

            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = self._as_sql(response)
            if sql:
                repaired.append(sql)

        # Execute the repaired candidates and choose the best one.
        executed_repairs = []
        for sql in sorted(repaired):
            result = self.execute(sql)
            executed_repairs.append({"sql": sql, "result": result})

        return self._select_best_repaired(executed_repairs)

    def _select_best_repaired(self, executed_repairs) -> str:
        if not executed_repairs:
            # Final generation produced no usable SQL.
            return ""

        ok_repairs = [entry for entry in executed_repairs if entry["result"].get("ok")]

        if ok_repairs:
            # Prefer successful executions, then more returned rows, then
            # lexicographically smallest SQL for deterministic tie-breaking.
            ok_repairs_sorted = sorted(
                ok_repairs,
                key=lambda entry: (
                    -len(entry["result"].get("rows") or []),
                    entry["sql"],
                ),
            )
            return ok_repairs_sorted[0]["sql"]

        # If none of the repairs executed cleanly, return the
        # lexicographically smallest repaired SQL deterministically.
        return sorted(executed_repairs, key=lambda entry: entry["sql"])[0]["sql"]

    @staticmethod
    def _as_sql(response) -> str:
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""

        text = response if isinstance(response, str) else str(response or "")
        return bridge.extract_sql(text)