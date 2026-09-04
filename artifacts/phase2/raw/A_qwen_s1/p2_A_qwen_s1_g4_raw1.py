"""Vote harness that samples several SQL candidates and selects the most consistent executable one."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS1G4(SQLHarness):
    def solve(self, question: str) -> str:
        schema = str(getattr(self, "schema", "") or "")

        samples = []
        sql_by_norm = {}
        order = []

        temperatures = [0.0, 0.1, 0.2]
        for idx, prompt in enumerate(self._candidate_prompts(question, schema)):
            raw = self._llm_text(prompt, self._system(), temperatures[idx % len(temperatures)])
            sql = self._extract_sql(raw)
            if not sql:
                continue

            norm = self._normalize_sql(sql)
            if not norm:
                continue

            samples.append(norm)
            if norm not in sql_by_norm:
                sql_by_norm[norm] = sql
                order.append(norm)

        if not order:
            prompt = self._base_prompt(
                question,
                schema,
                "Return exactly one executable SQL query and nothing else.",
            )
            raw = self._llm_text(prompt, self._system(), 0.0)
            sql = self._extract_sql(raw)
            return sql or self._clean_text(raw)

        freq = {}
        for norm in samples:
            freq[norm] = freq.get(norm, 0) + 1

        evaluated = []
        for idx, norm in enumerate(order):
            sql = sql_by_norm[norm]
            result = self._execute_safe(sql)
            ok = bool(result.get("ok"))
            rows = result.get("rows") or []
            signature = self._result_signature(rows) if ok else None

            evaluated.append(
                {
                    "sql": sql,
                    "ok": ok,
                    "signature": signature,
                    "frequency": freq.get(norm, 1),
                    "index": idx,
                }
            )

        ok_items = [item for item in evaluated if item["ok"]]
        if not ok_items:
            return sql_by_norm[order[0]]

        support = {}
        for item in ok_items:
            sig = item["signature"]
            support[sig] = support.get(sig, 0) + item["frequency"]

        best = None
        best_key = None
        for item in ok_items:
            sig_support = support.get(item["signature"], 0)
            # Prefer execution-result consensus, then sampling frequency, then brevity.
            key = (sig_support, item["frequency"], -len(item["sql"]), -item["index"])
            if best_key is None or key > best_key:
                best_key = key
                best = item["sql"]

        return best or sql_by_norm[order[0]]

    def _system(self) -> str:
        return (
            "You are a precise Text-to-SQL assistant. "
            "Write executable SQL for the given schema. "
            "Output only SQL, with no explanation and no markdown."
        )

    def _candidate_prompts(self, question: str, schema: str):
        return [
            self._base_prompt(
                question,
                schema,
                "Output only one executable SQL query.",
            ),
            self._base_prompt(
                question,
                schema,
                "Use explicit join conditions and only existing tables/columns. Output only SQL.",
            ),
            self._base_prompt(
                question,
                schema,
                "If the question is ambiguous, choose the most conventional interpretation. Output only SQL.",
            ),
        ]

    def _base_prompt(self, question: str, schema: str, extra: str) -> str:
        return f"""Schema:
{schema}

Question: {question}

{extra}
""".strip()

    def _llm_text(self, prompt: str, system: str, temperature: float) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        return self._response_to_text(response)

    def _response_to_text(self, response) -> str:
        if isinstance(response, list):
            return "\n".join(self._response_to_text(item) for item in response)

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "output", "sql"):
                if key in response:
                    return self._response_to_text(response[key])
            return str(response)

        return str(response or "")

    def _extract_sql(self, text: str) -> str:
        text = str(text or "")
        if not text.strip():
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted:
            return str(extracted).strip()

        return self._fallback_extract(text)

    def _fallback_extract(self, text: str) -> str:
        cleaned = self._clean_text(text)
        if not cleaned:
            return ""

        lower = cleaned.lower()
        if lower.startswith(("select", "with")):
            return cleaned

        for line in cleaned.splitlines():
            line = line.strip().strip("`").strip()
            if line.lower().startswith(("select", "with")):
                return line

        return cleaned

    def _clean_text(self, text: str) -> str:
        text = str(text or "").strip()

        if "