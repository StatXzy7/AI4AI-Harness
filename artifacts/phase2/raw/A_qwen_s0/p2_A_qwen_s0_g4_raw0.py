"""Generate multiple SQL candidates and choose one using execution-result voting."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G4(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert Text-to-SQL assistant. "
            "Return exactly one valid SQL SELECT statement and no explanation."
        )
        base_prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return only a single SQL query that answers the question."
        )
        prompts = [
            base_prompt,
            base_prompt
            + "\n\nPrefer explicit JOIN clauses and use only columns present in the schema.",
            base_prompt
            + "\n\nDouble-check filtering, grouping, and aggregation. Output only the SQL statement.",
        ]

        raw_samples = []
        candidates = []
        seen = set()

        def ingest(text):
            if text is None:
                return
            text = str(text)
            raw_samples.append(text)

            sql = self._extract_sql(text)
            if not sql:
                return

            key = self._normalize_sql(sql)
            if key and key not in seen:
                seen.add(key)
                candidates.append(sql)

        # Generate multiple candidate SQL queries.
        for prompt in prompts:
            try:
                response = self._call_llm(prompt, system=system, temperature=0.0, n=1)
            except Exception:
                continue

            for text in self._llm_texts(response):
                ingest(text)

        if not candidates:
            if raw_samples:
                fallback = self._extract_sql(raw_samples[0])
                if fallback:
                    return fallback
                return str(raw_samples[0]).strip()
            return ""

        # Execute candidates and vote on successful execution results.
        successful = []
        votes = {}

        for sql in candidates:
            result = self._execute_safe(sql)
            if result.get("ok"):
                sig = self._result_signature(result.get("rows"))
                successful.append((sql, sig))
                votes[sig] = votes.get(sig, 0) + 1

        if successful:
            preferred = [item for item in successful if self._looks_like_select(item[0])]
            pool = preferred if preferred else successful

            best_sql = pool[0][0]
            best_count = -1

            for sql, sig in pool:
                count = votes.get(sig, 0)
                if count > best_count:
                    best_count = count
                    best_sql = sql

            return best_sql

        # If nothing executed successfully, return the most plausible candidate.
        preferred = [sql for sql in candidates if self._looks_like_select(sql)]
        return preferred[0] if preferred else candidates[0]

    def _call_llm(self, prompt, system="", temperature=0.0, n=1):
        try:
            return self.llm(prompt, system=system, temperature=temperature, n=n)
        except (TypeError, ValueError):
            try:
                return self.llm(prompt, system=system, temperature=temperature)
            except (TypeError, ValueError):
                try:
                    return self.llm(prompt, system=system)
                except (TypeError, ValueError):
                    return self.llm(prompt)

    def _llm_texts(self, response):
        if response is None:
            return []

        if isinstance(response, str):
            return [response]

        if isinstance(response, bytes):
            return [response.decode("utf-8", "ignore")]

        if isinstance(response, (list, tuple)):
            out = []
            for item in response:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, bytes):
                    out.append(item.decode("utf-8", "ignore"))
                elif isinstance(item, dict):
                    for key in ("text", "completion", "content", "sql"):
                        value = item.get(key)
                        if isinstance(value, str):
                            out.append(value)
                            break
                    else:
                        out.append(str(item))
                elif hasattr(item, "text"):
                    out.append(str(item.text))
                else:
                    out.append(str(item))
            return out

        if hasattr(response, "choices"):
            out = []
            choices = getattr(response, "choices", []) or []
            for choice in choices:
                if hasattr(choice, "text"):
                    out.append(str(choice.text))
                elif hasattr(choice, "message") and hasattr(choice.message, "content"):
                    out.append(str(choice.message.content))
                elif isinstance(choice, dict):
                    for key in ("text", "content"):
                        value = choice.get(key)
                        if isinstance(value, str):
                            out.append(value)
                            break
            if out:
                return out

        if isinstance(response, dict):
            if "choices" in response:
                return self._llm_texts(response["choices"])

            for key in ("text", "completion", "content", "sql"):
                value = response.get(key)
                if isinstance(value, str):
                    return [value]
                if isinstance(value, (list, tuple)):
                    return self._llm_texts(value)

        return [str(response)]

    def _extract_sql(self, text):
        if text is None:
            return ""

        text = str(text)

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = text

        if sql is None:
            sql = text

        if isinstance(sql, (list, tuple)):
            sql = sql[0] if sql else ""

        sql = str(sql).strip()
        if not sql:
            return ""

        while sql.endswith(";"):
            sql = sql[:-1].strip()

        return sql

    def _normalize_sql(self, sql):
        return " ".join(str(sql).lower().split())

    def _execute_safe(self, sql):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {
            "ok": bool(result),
            "rows": getattr(result, "rows", []),
            "error": "",
        }

    def _result_signature(self, rows):
        if isinstance(rows, dict):
            row_list = [rows]
        else:
            try:
                row_list = list(rows or [])
            except Exception:
                row_list = []

        normalized = []
        for row in row_list[:200]:
            try:
                if isinstance(row, dict):
                    normalized.append(
                        tuple(sorted((str(k), str(v)) for k, v in row.items()))
                    )
                elif isinstance(row, (list, tuple)):
                    normalized.append(tuple(str(v) for v in row))
                else:
                    normalized.append((str(row),))
            except Exception:
                normalized.append((repr(row),))

        try:
            normalized = sorted(normalized)
        except Exception:
            pass

        return (len(row_list), repr(normalized)[:4000])

    def _looks_like_select(self, sql):
        s = str(sql).lower().strip()
        return s.startswith("select") or s.startswith("with")