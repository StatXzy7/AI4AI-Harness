"""Generates SQL, executes it, classifies failures as syntax/schema/semantic, and applies class-specific repairs for up to two rounds."""

try:
    from ..harness_base import SQLHarness
    from .. import bridge
except ImportError:
    from harness_base import SQLHarness
    import bridge


class P2P2DQwenS0ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = str(getattr(self, "schema", "") or "")
        attempts = []

        raw = self._call_llm(
            self._initial_prompt(question, schema),
            system=self._system_for("initial"),
        )
        sql = self._extract_sql(raw)
        result = self._execute_sql(sql)
        attempts.append(self._make_attempt("initial", sql, result))

        if result.get("ok"):
            return sql or "SELECT 1"

        failure_class = self._classify_failure(sql, result)

        for round_no in range(1, self.MAX_REPAIR_ROUNDS + 1):
            prompt = self._repair_prompt(
                failure_class=failure_class,
                question=question,
                schema=schema,
                sql=sql,
                result=result,
                attempts=attempts,
                round_no=round_no,
            )
            raw = self._call_llm(prompt, system=self._system_for(failure_class))
            new_sql = self._extract_sql(raw)

            if not new_sql:
                result = {
                    "ok": False,
                    "rows": [],
                    "error": "No SQL could be extracted from the repair response.",
                }
                attempts.append(
                    self._make_attempt(
                        f"{failure_class}-repair-{round_no}-empty",
                        sql,
                        result,
                    )
                )
                failure_class = "syntax"
                continue

            sql = new_sql
            result = self._execute_sql(sql)
            attempts.append(
                self._make_attempt(f"{failure_class}-repair-{round_no}", sql, result)
            )

            if result.get("ok"):
                return sql

            failure_class = self._classify_failure(sql, result)

        return sql or "SELECT 1"

    def _call_llm(self, prompt, system=""):
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                response = self.llm(prompt, system=system, temperature=0.0)
            except TypeError:
                try:
                    response = self.llm(prompt)
                except Exception:
                    return ""
            except Exception:
                return ""
        except Exception:
            return ""

        if isinstance(response, bytes):
            return response.decode("utf-8", "ignore")
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        if isinstance(response, dict):
            for key in ("text", "completion", "content", "response", "sql", "output"):
                value = response.get(key)
                if isinstance(value, str):
                    return value
            return str(response)
        return str(response or "")

    def _extract_sql(self, text):
        text = str(text or "")
        if not text.strip():
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        sql = str(sql or "").strip()
        if sql:
            return self._trim_to_single_statement(sql)

        return self._heuristic_extract_sql(text)

    def _heuristic_extract_sql(self, text):
        lowered = text.lower()
        fence_start = lowered.find("