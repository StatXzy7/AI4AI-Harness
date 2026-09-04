"""Sample multiple SQL candidates and choose the best executable result by voting."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert SQL engineer. Produce only one executable SQLite SELECT statement. "
            "No explanations, no Markdown."
        )
        prompts = [
            f"Schema:\n{schema}\n\nQuestion: {question}\n\nSQL:",
            f"Write a SQLite SELECT query that answers the question using the schema below.\nSchema:\n{schema}\n\nQuestion: {question}\n\nSELECT query:",
            f"Given this schema and question, output the exact SQL SELECT statement only.\nSchema:\n{schema}\n\nQuestion: {question}",
        ]
        temperatures = [0.0, 0.4, 0.8]

        unique = {}
        order = []

        for prompt, temperature in zip(prompts, temperatures):
            text = self._llm_text(prompt, system, temperature)
            sql = self._extract_sql(text)
            norm = self._normalize_sql(sql)

            if not norm:
                continue

            if norm in unique:
                unique[norm]["votes"] += 1
            else:
                unique[norm] = {"sql": sql, "votes": 1}
                order.append(norm)

        if not order:
            text = self._llm_text(prompts[0], system, 0.0)
            sql = self._extract_sql(text)
            return sql or "SELECT 1"

        result_groups = {}
        failed = []

        for norm in order:
            cand = unique[norm]
            sql = cand["sql"]

            if not self._looks_like_select(sql):
                failed.append(cand)
                continue

            res = self._execute(sql)

            if res.get("ok"):
                rows = res.get("rows") or []
                sig = self._rows_signature(rows)

                if sig not in result_groups:
                    result_groups[sig] = {
                        "votes": 0,
                        "sql": sql,
                        "row_count": self._row_count(rows),
                    }
                else:
                    if len(sql) < len(result_groups[sig]["sql"]):
                        result_groups[sig]["sql"] = sql

                result_groups[sig]["votes"] += cand["votes"]
            else:
                failed.append(cand)

        if result_groups:
            best = max(
                result_groups.values(),
                key=lambda g: (g["votes"], 1 if g["row_count"] else 0, -len(g["sql"])),
            )
            return best["sql"]

        return min((unique[n]["sql"] for n in order), key=len)

    def _llm_text(self, prompt, system, temperature):
        try:
            resp = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        return self._stringify(resp)

    def _stringify(self, resp):
        if resp is None:
            return ""
        if isinstance(resp, str):
            return resp
        if isinstance(resp, (list, tuple)):
            return "\n".join(self._stringify(item) for item in resp)
        if isinstance(resp, dict):
            for key in ("text", "output", "completion", "content", "result", "generated_text", "message"):
                if key in resp:
                    return self._stringify(resp[key])
            if "choices" in resp:
                choices = resp.get("choices")
                if isinstance(choices, (list, tuple)) and choices:
                    return self._stringify(choices[0])
            return str(resp)

        for attr in ("text", "output", "content", "message"):
            if hasattr(resp, attr):
                return self._stringify(getattr(resp, attr))

        if hasattr(resp, "choices"):
            choices = getattr(resp, "choices")
            if isinstance(choices, (list, tuple)) and choices:
                return self._stringify(choices[0])

        return str(resp)

    def _extract_sql(self, text):
        text = text or ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = text

        sql = (sql or "").strip()
        if not sql:
            sql = text.strip()

        sql = sql.strip().rstrip(";").strip()
        return sql

    def _normalize_sql(self, sql):
        return " ".join((sql or "").strip().lower().split())

    def _looks_like_select(self, sql):
        s = (sql or "").strip().lower()
        return s.startswith("select") or s.startswith("with")

    def _execute(self, sql):
        try:
            res = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(res, dict):
            if "ok" not in res:
                res["ok"] = not res.get("error")
            if "rows" not in res:
                res["rows"] = []
            return res

        return {
            "ok": bool(res),
            "rows": getattr(res, "rows", []),
            "error": getattr(res, "error", ""),
        }

    def _row_count(self, rows):
        try:
            return len(rows)
        except Exception:
            return 0

    def _rows_signature(self, rows):
        try:
            sample = []

            for i, row in enumerate(rows):
                if i >= 20:
                    break

                if hasattr(row, "keys"):
                    try:
                        keys = list(row.keys())
                        sample.append(tuple((str(k), self._cell_repr(row[k])) for k in keys))
                        continue
                    except Exception:
                        pass

                if isinstance(row, dict):
                    sample.append(tuple(sorted((str(k), self._cell_repr(v)) for k, v in row.items())))
                elif isinstance(row, (list, tuple)):
                    sample.append(tuple(self._cell_repr(v) for v in row))
                elif isinstance(row, (str, bytes, int, float, bool)) or row is None:
                    sample.append(self._cell_repr(row))
                else:
                    try:
                        sample.append(tuple(self._cell_repr(v) for v in row))
                    except Exception:
                        sample.append(self._cell_repr(row))

            return repr((self._row_count(rows), sample))
        except Exception:
            return str(rows)[:2000]

    def _cell_repr(self, value):
        try:
            s = repr(value)
        except Exception:
            s = str(value)

        if len(s) > 120:
            s = s[:117] + "..."

        return s