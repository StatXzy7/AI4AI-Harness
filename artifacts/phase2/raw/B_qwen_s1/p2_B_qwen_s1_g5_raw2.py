"""Generate multiple SQL samples and select the best candidate using execution-based voting."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS1G5(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert text-to-SQL model. Output only one valid SQL query."
        base_prompt = (
            "Schema:\n"
            f"{self.schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Return only the SQL query."
        )

        prompts = [
            base_prompt + "\n\nPrefer the simplest correct query.",
            base_prompt + "\n\nBe careful to use exact table and column names from the schema.",
            base_prompt + "\n\nConsider joins, filtering, aggregation, and ordering if needed.",
        ]

        samples = []
        for prompt in prompts:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            raw = response if isinstance(response, str) else str(response)
            sql = self._extract_sql(raw)
            if sql:
                samples.append(sql)

        if not samples:
            return ""

        infos = []
        for idx, sql in enumerate(samples):
            result = self.execute(sql)
            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": "Unexpected execution result."}

            ok = bool(result.get("ok"))
            rows = []
            if ok:
                try:
                    rows = list(result.get("rows") or [])
                except TypeError:
                    rows = []

            error = str(result.get("error", "")) if not ok else ""
            infos.append(
                {
                    "idx": idx,
                    "sql": sql,
                    "ok": ok,
                    "rows": rows,
                    "error": error,
                    "signature": self._signature(rows) if ok else None,
                }
            )

        ok_infos = [info for info in infos if info["ok"]]
        if not ok_infos:
            return samples[0]

        if len(ok_infos) == 1:
            return ok_infos[0]["sql"]

        counts = {}
        first_idx = {}
        for info in ok_infos:
            sig = info["signature"]
            counts[sig] = counts.get(sig, 0) + 1
            if sig not in first_idx:
                first_idx[sig] = info["idx"]

        best_sig = max(counts.items(), key=lambda item: (item[1], -first_idx[item[0]]))[0]
        majority = [info for info in ok_infos if info["signature"] == best_sig]

        if counts[best_sig] > 1:
            return majority[0]["sql"]

        judged = self._judge(question, ok_infos)
        if judged is not None:
            return judged

        return majority[0]["sql"]

    def _judge(self, question: str, infos):
        blocks = []
        for i, info in enumerate(infos):
            preview = self._rows_preview(info["rows"])
            blocks.append(f"Candidate {i + 1}:\n{info['sql']}\nResult preview:\n{preview}")

        prompt = (
            "Schema:\n"
            f"{self.schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Several candidate SQL queries executed successfully. "
            "Choose the one that best answers the question. "
            "Ignore style; focus on semantic correctness.\n\n"
            + "\n\n".join(blocks)
            + "\n\nReply with only the candidate number."
        )

        try:
            response = self.llm(
                prompt,
                system="You are a SQL evaluation judge. Output only a candidate number.",
                temperature=0.0,
                n=1,
            )
        except Exception:
            return None

        text = str(response).strip()
        numbers = []
        current = ""
        for ch in text:
            if ch.isdigit():
                current += ch
            elif current:
                numbers.append(int(current))
                current = ""
        if current:
            numbers.append(int(current))

        for value in numbers:
            if 1 <= value <= len(infos):
                return infos[value - 1]["sql"]

        return None

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = None

        if extracted:
            return self._clean_sql(str(extracted))

        candidate = self._strip_markdown(str(text)).strip()
        if candidate.lower().startswith(("select", "with")):
            return self._clean_sql(candidate)

        collected = []
        collecting = False
        for line in candidate.splitlines():
            stripped = line.strip()
            lowered = stripped.lower()

            if not collecting and lowered.startswith(("select", "with")):
                collecting = True

            if collecting:
                if lowered.startswith(("question:", "schema:", "answer:", "explanation:")):
                    break
                collected.append(line.rstrip())

        if collected:
            return self._clean_sql("\n".join(collected))

        return ""

    def _strip_markdown(self, text: str) -> str:
        if "