"""Repair mechanism: execute SQL and feed errors back for regeneration, with multi-attempt diversity."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2AMinimaxS2G4(SQLHarness):
    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        schema = self.schema
        best_sql = None
        best_score = (-1, float("inf"))  # (success_flag, -error_penalty)

        base_system = (
            "You are an expert SQL writer. Given a database schema and a natural language "
            "question, produce a single valid SQL query. Output ONLY the SQL — no prose, "
            "no markdown fences, no explanation. The SQL must be executable on the given schema."
        )

        history = []
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # Build a prompt that escalates with feedback
            if attempt == 0:
                user_prompt = (
                    f"Schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Write the SQL query."
                )
            elif attempt == 1:
                # Force a fresh alternative formulation
                user_prompt = (
                    f"Schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Your previous attempt failed. Try a fundamentally different "
                    f"SQL formulation — e.g., different JOIN order, subquery vs. JOIN, "
                    f"different aggregation level.\n\n"
                    f"Previous attempt:\n{last_sql}\n\n"
                    f"Write a new SQL query."
                )
            else:
                # Repair using the most recent concrete execution feedback
                err = history[-1]["error"] if history else ""
                user_prompt = (
                    f"Schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Your SQL failed to execute with this error:\n{err}\n\n"
                    f"Failed SQL:\n{last_sql}\n\n"
                    f"Fix the SQL so it executes successfully. Output ONLY the corrected SQL."
                )

            try:
                raw = self.llm(user_prompt, system=base_system, temperature=0.0, n=1)
            except Exception as e:
                history.append({"sql": last_sql, "error": f"LLM call failed: {e}", "ok": False})
                continue

            if not raw:
                continue

            sql = bridge.extract_sql(raw)
            if not sql:
                # Last-resort: try to fish out anything that looks like SQL
                m = re.search(r"(SELECT|INSERT|UPDATE|DELETE|WITH)\b.*?(;|\Z)",
                              raw, "flags" and 0 or 0)
                if m:
                    sql = m.group(0).strip().rstrip(";").strip()
                else:
                    history.append({"sql": "", "error": "Could not extract SQL", "ok": False})
                    continue

            # Execute and score
            try:
                result = self.execute(sql)
            except Exception as e:
                history.append({"sql": sql, "error": f"execute() raised: {e}", "ok": False})
                last_sql = sql
                continue

            ok = bool(result.get("ok"))
            err = (result.get("error") or "") if isinstance(result, dict) else ""
            rows = result.get("rows") if isinstance(result, dict) else None

            history.append({"sql": sql, "error": err, "ok": ok, "rows": rows})

            # Score: prefer executable; tiebreak on row count (more results is a soft proxy
            # for having actually answered the question)
            score = (1 if ok else 0, len(rows) if (ok and rows is not None) else 0)
            if score > best_score:
                best_score = score
                best_sql = sql

            if ok:
                # Successful execution — accept and stop
                return sql

            last_sql = sql

        # No successful execution — return the best candidate we have (even if it didn't run),
        # otherwise fall back to whatever SQL we last saw.
        if best_sql:
            return best_sql
        if last_sql:
            return last_sql
        return ""