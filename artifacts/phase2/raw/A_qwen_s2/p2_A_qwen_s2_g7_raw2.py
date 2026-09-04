"""Harness that samples multiple SQL candidates and selects one by execution consensus."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQL engineer. Produce only a single valid SQL query. "
            "Do not include explanations, comments, or markdown."
        )

        base_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question using only the schema above."
        )

        variants = [
            "Return only the SQL query text.",
            "Be careful with table names, column names, and filtering values. Return only the final SQL query text.",
            "Prefer simple, executable SQL. Return only the SQL query text.",
        ]
        temperatures = [0.0, 0.4, 0.8]

        candidates = []
        seen = {}
        last_raw = ""

        for idx, variant in enumerate(variants):
            prompt = base_prompt + "\n\n" + variant
            try:
                raw = self.llm(
                    prompt,
                    system=system,
                    temperature=temperatures[idx % len(temperatures)],
                    n=1,
                )
            except Exception:
                continue

            raw_text = raw if isinstance(raw, str) else str(raw)
            last_raw = raw_text.strip()

            try:
                extracted = bridge.extract_sql(raw_text)
            except Exception:
                extracted = ""

            sql = (extracted or "").strip()

            if not sql:
                stripped = raw_text.strip()
                if stripped.lower().startswith(("select", "with", "insert", "update", "delete")):
                    sql = stripped

            if not sql:
                continue

            norm = self._normalize_sql(sql)
            if norm in seen:
                seen[norm]["votes"] += 1
                continue

            entry = {
                "sql": sql,
                "norm": norm,
                "votes": 1,
                "ok": False,
                "rows": [],
                "error": "not executed",
            }
            seen[norm] = entry
            candidates.append(entry)

        if not candidates:
            return last_raw

        for cand in candidates:
            try:
                result = self.execute(cand["sql"])
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": "Execution result was not a dictionary."}

            cand["ok"] = bool(result.get("ok"))
            rows = result.get("rows")
            cand["rows"] = rows if rows is not None else []
            cand["error"] = "" if cand["ok"] else (result.get("error") or "")

        ok_candidates = [c for c in candidates if c["ok"]]

        if ok_candidates:
            groups = {}
            order = []

            for cand in ok_candidates:
                fp = self._fingerprint_rows(cand["rows"])
                if fp not in groups:
                    groups[fp] = {"votes": 0, "members": []}
                    order.append(fp)

                groups[fp]["votes"] += cand["votes"]
                groups[fp]["members"].append(cand)

            best_fp = None
            best_score = None

            for idx, fp in enumerate(order):
                shortest_sql_len = min(len(member["sql"]) for member in groups[fp]["members"])
                score = (groups[fp]["votes"], -idx, -shortest_sql_len)

                if best_score is None or score > best_score:
                    best_score = score
                    best_fp = fp

            chosen_group = groups[best_fp]
            chosen = min(chosen_group["members"], key=lambda c: (len(c["sql"]), c["sql"]))
            return chosen["sql"]

        best = max(candidates, key=lambda c: (c["votes"], -len(c["sql"])))
        return best["sql"]

    def _normalize_sql(self, sql: str) -> str:
        return " ".join(sql.strip().rstrip(";").split()).lower()

    def _fingerprint_rows(self, rows) -> str:
        try:
            return repr(self._make_hashable(rows))
        except Exception:
            return str(rows)

    def _make_hashable(self, value):
        if isinstance(value, dict):
            return tuple(sorted((str(k), self._make_hashable(v)) for k, v in value.items()))
        if isinstance(value, (list, tuple)):
            return tuple(self._make_hashable(item) for item in value)
        return value