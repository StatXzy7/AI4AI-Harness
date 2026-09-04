"""Harness samples multiple SQL candidates and selects among them by execution agreement and judging."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""

        candidates = self._generate_candidates(question, schema)
        if not candidates:
            fallback = self._generate_one(question, schema, 0, 0.0)
            if fallback:
                return fallback
            return "SELECT 1"

        self._execute_candidates(candidates)
        selected = self._select_candidate(question, schema, candidates)

        if selected and selected.get("sql"):
            return selected["sql"]
        return candidates[0].get("sql", "SELECT 1")

    def _generate_candidates(self, question, schema):
        candidates = []
        index_by_norm = {}

        # Three lightly diversified greedy/low-temperature samples.
        variants = (
            (0.0, 0),
            (0.2, 1),
            (0.5, 2),
        )

        for temperature, variant in variants:
            sql = self._generate_one(question, schema, variant, temperature)
            if not sql:
                continue

            norm = self._normalize_sql(sql)
            if not norm:
                continue

            if norm in index_by_norm:
                candidates[index_by_norm[norm]]["votes"] += 1
            else:
                index_by_norm[norm] = len(candidates)
                candidates.append(
                    {
                        "sql": sql,
                        "norm": norm,
                        "votes": 1,
                        "ok": False,
                        "rows": [],
                        "row_count": 0,
                        "error": "",
                        "fingerprint": None,
                    }
                )

        return candidates

    def _generate_one(self, question, schema, variant, temperature):
        prompt = self._generation_prompt(question, schema, variant)
        try:
            raw = self.llm(
                prompt,
                system=self._generator_system(),
                temperature=temperature,
                n=1,
            )
        except Exception:
            return ""

        text = self._llm_text(raw)
        sql = self._extract_sql(text)
        if not sql:
            return ""
        return self._clean_sql(sql)

    def _generation_prompt(self, question, schema, variant):
        schema_text = str(schema) if schema else "(no schema provided)"
        if len(schema_text) > 12000:
            schema_text = schema_text[:12000] + "\n-- schema truncated --"

        base = f"Schema:\n{schema_text}\n\nQuestion: {question}\n\n"

        if variant == 0:
            return base + "Write SQL that answers the question. Return only the SQL statement."
        if variant == 1:
            return (
                base
                + "Carefully identify the needed tables, joins, and filters, then write SQL. "
                + "Return only the final SQL statement."
            )
        return (
            base
            + "Write the simplest single SELECT statement that answers the question. "
            + "Return only SQL."
        )

    def _generator_system(self):
        return (
            "You are a precise Text-to-SQL model. "
            "Output only one executable SQL statement, with no Markdown and no explanation."
        )

    def _execute_candidates(self, candidates):
        for cand in candidates:
            result = self._safe_execute(cand["sql"])
            ok = bool(result.get("ok")) if isinstance(result, dict) else False
            rows = result.get("rows") if ok else []
            if rows is None:
                rows = []

            cand["ok"] = ok
            cand["rows"] = rows
            cand["row_count"] = self._row_count(rows)
            cand["error"] = "" if ok else str(result.get("error", ""))
            cand["fingerprint"] = self._fingerprint(rows) if ok else "error:" + cand["error"][:200]

    def _safe_execute(self, sql):
        try:
            result = self.execute(sql)
            if isinstance(result, dict):
                return result
            return {"ok": True, "rows": result, "error": ""}
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _select_candidate(self, question, schema, candidates):
        successful = [c for c in candidates if c.get("ok")]

        if successful:
            groups = {}
            for cand in successful:
                groups.setdefault(cand.get("fingerprint"), []).append(cand)

            def group_score(group):
                total_votes = sum(c.get("votes", 1) for c in group)
                nonempty = 1 if any(c.get("row_count", 0) > 0 for c in group) else 0
                shortest_sql = min(len(str(c.get("sql", ""))) for c in group)
                return (total_votes, nonempty, -shortest_sql)

            best_group = max(groups.values(), key=group_score)
            best = min(
                best_group,
                key=lambda c: (len(str(c.get("sql", ""))), str(c.get("sql", ""))),
            )

            best_votes = sum(c.get("votes", 1) for c in best_group)
            if best_votes > 1 or len(successful) == 1:
                return best

            judged = self._judge(question, schema, successful)
            if judged is not None:
                return judged
            return best

        judged = self._judge(question, schema, candidates)
        if judged is not None:
            return judged

        return min(
            candidates,
            key=lambda c: (
                -c.get("votes", 1),
                len(str(c.get("error", ""))),
                len(str(c.get("sql", ""))),
            ),
        )

    def _judge(self, question, schema, candidates):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        lines = []
        lines.append("Choose the best SQL option for the question.")
        lines.append(f"Question: {question}")

        schema_text = str(schema) if schema else ""
        if schema_text:
            if len(schema_text) > 4000:
                schema_text = schema_text[:4000] + "\n-- schema truncated --"
            lines.append(f"Schema:\n{schema_text}")

        for i, cand in enumerate(candidates):
            status = "OK" if cand.get("ok") else "FAILED"
            row_count = cand.get("row_count", 0)
            error = str(cand.get("error", ""))[:200]
            sql = str(cand.get("sql", ""))
            lines.append(
                f"Option {i + 1}: status={status}; row_count={row_count}; "
                f"error={error}; sql={sql}"
            )

            if cand.get("ok"):
                preview = self._preview_rows(cand.get("rows"), max_rows=3, max_cols=5)
                if preview:
                    lines.append(f"Sample rows {i + 1}: {preview}")

        lines.append("Return only the option number as a single integer.")
        prompt = "\n".join(lines)

        try:
            raw = self.llm(
                prompt,
                system="You are an exact SQL selector. Reply with one integer only.",
                temperature=0.0,
                n=1,
            )
        except Exception:
            return None

        text = self._llm_text(raw)
        idx = self._parse_index(text, len(candidates))
        if idx is None:
            return None
        return candidates[idx]

    def _parse_index(self, text, limit):
        text = str(text or "")

        tokens = text.replace("Option", " ").replace("option", " ").split()
        for token in tokens:
            cleaned = token.strip().strip(".,:;()[]{}'\"")
            if cleaned.isdigit():
                value = int(cleaned)
                if 1 <= value <= limit:
                    return value - 1
                if 0 <= value < limit:
                    return value

        numbers = []
        current = ""
        for ch in text:
            if ch.isdigit():
                current += ch
            else:
                if current:
                    numbers.append(int(current))
                    current = ""
        if current:
            numbers.append(int(current))

        for value in numbers:
            if 1 <= value <= limit:
                return value - 1
            if 0 <= value < limit:
                return value

        return None

    def _preview_rows(self, rows, max_rows=3, max_cols=5):
        try:
            if rows is None:
                return "[]"
            if isinstance(rows, dict):
                rows = [rows]

            preview = []
            for i, row in enumerate(rows):
                if i >= max_rows:
                    break

                if isinstance(row, dict):
                    items = list(row.items())[:max_cols]
                    preview.append({str(k): self._preview_value(v) for k, v in items})
                elif isinstance(row, (list, tuple)):
                    preview.append([self._preview_value(v) for v in list(row)[:max_cols]])
                else:
                    preview.append(self._preview_value(row))

            return str(preview)
        except Exception:
            return "[unpreviewable]"

    def _preview_value(self, value):
        try:
            text = str(value)
        except Exception:
            text = repr(value)
        if len(text) > 50:
            text = text[:50] + "..."
        return text

    def _fingerprint(self, rows):
        try:
            count = self._row_count(rows)

            if rows is None:
                iterable = []
            elif isinstance(rows, (list, tuple)):
                iterable = rows
            elif isinstance(rows, dict):
                iterable = [rows]
            else:
                iterable = [rows]

            normalized = []
            for i, row in enumerate(iterable):
                if i >= 100:
                    break
                normalized.append(self._normalize_row(row))

            try:
                normalized.sort()
            except Exception:
                pass

            return f"count={count}|rows=" + ";".join(normalized)
        except Exception:
            return "unfingerprintable"

    def _normalize_row(self, row):
        try:
            if isinstance(row, dict):
                parts = []
                for key in sorted(row.keys(), key=str):
                    parts.append(f"{key}:{self._canonical_value(row[key])}")
                return "|".join(parts)

            if isinstance(row, (list, tuple)):
                return "|".join(self._canonical_value(v) for v in row)

            return self._canonical_value(row)
        except Exception:
            return "badrow"

    def _canonical_value(self, value):
        if value is None:
            return "NULL"

        if isinstance(value, (int, float, bool)):
            return str(value)

        try:
            if isinstance(value, bytes):
                text = repr(value)
            else:
                text = str(value)
        except Exception:
            text = repr(value)

        if len(text) > 120:
            text = text[:120] + "..."
        return text

    def _row_count(self, rows):
        if rows is None:
            return 0
        if isinstance(rows, (list, tuple, dict)):
            return len(rows)
        try:
            return len(rows)
        except Exception:
            return 1

    def _extract_sql(self, text):
        try:
            sql = bridge.extract_sql(text)
            if sql and str(sql).strip():
                return str(sql)
        except Exception:
            pass
        return self._fallback_extract(text)

    def _fallback_extract(self, text):
        if not text:
            return ""

        txt = str(text).strip()

        if "