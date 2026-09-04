"""Sample multiple SQL candidates and select one by execution-based voting."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS1G1(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a precise SQL assistant. Output only one executable SQL query."
        base_prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Answer this question with SQL:\n{question}\n\n"
            "SQL only:"
        )

        variants = [
            ("Write the most direct SQL query.", 0.1),
            ("Write a robust SQL query that avoids unnecessary columns.", 0.5),
            ("Write an alternative SQL query that still answers the question.", 0.8),
        ]

        candidates = []
        for extra_instruction, temperature in variants:
            prompt = base_prompt + "\n\n" + extra_instruction

            try:
                raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                raw = ""

            if isinstance(raw, (list, tuple)):
                raw = raw[0] if len(raw) else ""

            raw = str(raw or "")

            try:
                sql = bridge.extract_sql(raw)
            except Exception:
                sql = None

            sql = str(sql or "").strip()
            if not sql:
                sql = raw.strip()

            if sql:
                candidates.append({"sql": sql, "raw": raw})

        if not candidates:
            try:
                raw = self.llm(base_prompt, system=system, temperature=0.0, n=1)
            except Exception:
                raw = ""

            if isinstance(raw, (list, tuple)):
                raw = raw[0] if len(raw) else ""

            raw = str(raw or "")

            try:
                sql = bridge.extract_sql(raw)
            except Exception:
                sql = None

            sql = str(sql or "").strip() or raw.strip()
            return sql or "SELECT 1"

        executed = []
        for idx, candidate in enumerate(candidates):
            try:
                result = self.execute(candidate["sql"])
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": "invalid executor result"}

            ok = bool(result.get("ok", False))
            rows = result.get("rows", [])

            try:
                row_count = len(rows)
            except Exception:
                row_count = 0

            try:
                fingerprint = repr(rows)
            except Exception:
                fingerprint = str(rows)

            if len(fingerprint) > 4000:
                fingerprint = fingerprint[:4000]

            executed.append(
                {
                    "idx": idx,
                    "sql": candidate["sql"],
                    "ok": ok,
                    "row_count": row_count,
                    "fingerprint": fingerprint,
                }
            )

        ok_groups = {}
        for item in executed:
            if item["ok"]:
                ok_groups.setdefault(item["fingerprint"], []).append(item)

        if ok_groups:
            best_items = max(
                ok_groups.values(),
                key=lambda items: (len(items), -min(it["idx"] for it in items)),
            )
            return best_items[0]["sql"]

        text_votes = {}
        for item in executed:
            normalized_sql = " ".join(item["sql"].lower().split())
            entry = text_votes.setdefault(
                normalized_sql,
                {"count": 0, "idx": item["idx"], "sql": item["sql"]},
            )
            entry["count"] += 1
            if item["idx"] < entry["idx"]:
                entry["idx"] = item["idx"]

        if text_votes:
            best = min(text_votes.values(), key=lambda entry: (-entry["count"], entry["idx"]))
            return best["sql"]

        return candidates[0]["sql"]