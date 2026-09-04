"""Sample multiple SQL candidates and select one by execution-based voting."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = str(getattr(self, "schema", "") or "")
        system = (
            "You are an expert Text-to-SQL system. Write exactly one executable SQL query "
            "that answers the question. Return only SQL, without explanations or markdown."
        )
        prompt = self._generation_prompt(schema, question)

        candidates = []
        for temperature in (0.0, 0.2, 0.4):
            text = self._safe_llm(prompt, system=system, temperature=temperature)
            sql = self._extract_sql(text)
            if sql:
                candidates.append(sql)

        if not candidates:
            text = self._safe_llm(
                self._fallback_prompt(schema, question),
                system=system,
                temperature=0.0,
            )
            sql = self._extract_sql(text)
            if sql:
                candidates.append(sql)

        if not candidates:
            return "SELECT 1"

        unique = []
        original = {}
        counts = {}

        for sql in candidates:
            norm = self._normalize_sql(sql)
            counts[norm] = counts.get(norm, 0) + 1
            if norm not in original:
                original[norm] = sql
                unique.append(norm)

        records = []
        fingerprints = {}

        for norm in unique:
            sql = original[norm]
            result = self._safe_execute(sql)
            ok = bool(result.get("ok"))
            fingerprint = self._result_fingerprint(result) if ok else None

            if ok:
                fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1

            records.append(
                {
                    "sql": sql,
                    "norm": norm,
                    "ok": ok,
                    "fingerprint": fingerprint,
                    "error": str(result.get("error") or ""),
                }
            )

        best_sql = candidates[0]
        best_score = None

        for rec in records:
            score = 0.0

            if rec["ok"]:
                score += 10000.0
                score += 100.0 * fingerprints.get(rec["fingerprint"], 0)

            score += 1000.0 * counts.get(rec["norm"], 0)
            score -= min(len(rec["sql"]) / 1000.0, 10.0)

            if best_score is None or score > best_score:
                best_score = score
                best_sql = rec["sql"]

        return best_sql.strip()

    def _safe_llm(self, prompt, system="", temperature=0.0):
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            try:
                response = self.llm(prompt, system=system, temperature=temperature)
            except TypeError:
                try:
                    response = self.llm(prompt)
                except Exception:
                    return ""
            except Exception:
                return ""
        except Exception:
            return ""

        return self._response_text(response)

    def _response_text(self, response):
        if response is None:
            return ""

        if isinstance(response, str):
            return response

        if isinstance(response, list):
            return self._response_text(response[0]) if response else ""

        if isinstance(response, dict):
            for key in ("text", "completion", "output", "content"):
                if key in response:
                    return self._response_text(response[key])

            if "choices" in response:
                choices = response.get("choices") or []
                if choices:
                    return self._response_text(choices[0])

            if "message" in response:
                return self._response_text(response["message"])

        return str(response)

    def _extract_sql(self, text):
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = None

        sql = str(extracted or "").strip()
        if not sql:
            sql = text.strip().strip("`").strip()

        return sql.strip()

    def _safe_execute(self, sql):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"ok": bool(result), "rows": [], "error": ""}

    def _normalize_sql(self, sql):
        return " ".join(str(sql).lower().replace(";", " ").split())

    def _result_fingerprint(self, result):
        rows = result.get("rows", [])
        try:
            row_count = len(rows)
        except Exception:
            row_count = 0

        sample = ""
        try:
            if row_count:
                sample = repr(rows[0])[:200]
        except Exception:
            sample = ""

        return (row_count, sample)

    def _generation_prompt(self, schema, question):
        return (
            "Given the following database schema:\n"
            f"{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write one SQL query that answers the question. Output only the SQL query."
        )

    def _fallback_prompt(self, schema, question):
        return (
            "The previous attempt failed to produce SQL. "
            "Return only a single executable SQL query.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n"
        )