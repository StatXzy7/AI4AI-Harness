"""Generate multiple SQL candidates and select the best one by executing them and voting on consistent results."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G5(SQLHarness):
    def solve(self, question: str) -> str:
        candidates = self._generate_candidates(question)

        if not candidates:
            return self._fallback_generate(question)

        successful = []
        votes = {}

        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "rows": []}

            if isinstance(result, dict) and result.get("ok"):
                signature = self._result_signature(result.get("rows"))
                successful.append((sql, signature))
                votes[signature] = votes.get(signature, 0) + 1

        if successful:
            best_vote_count = max(votes.values())

            if best_vote_count > 1:
                for sql, signature in successful:
                    if votes.get(signature) == best_vote_count:
                        return sql

            chosen = self._choose_candidate(question, [sql for sql, _ in successful])
            return chosen or successful[0][0]

        chosen = self._choose_candidate(question, candidates)
        return chosen or candidates[0]

    def _generate_candidates(self, question):
        specs = [
            (
                "You are an expert Text-to-SQL system. Return only one valid SQL query.",
                "Write a SQL query that answers the question using the schema.",
            ),
            (
                "You are a careful database engineer. Output a single executable SQL query only.",
                "Using the schema below, produce the most precise SQL query for the question.",
            ),
            (
                "You translate natural language questions into SQL. Respond with only SQL.",
                "Given the schema and question, generate one correct SQL query.",
            ),
        ]

        candidates = []
        seen = set()

        for system, intro in specs:
            prompt = (
                f"{intro}\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"SQL:"
            )

            response = self._llm_text(prompt, system=system, temperature=0.3)
            sql = self._extract_sql(response)
            normalized = self._normalize(sql)

            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(sql.strip())

        return candidates

    def _fallback_generate(self, question):
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Return only the SQL query."
        )
        response = self._llm_text(
            prompt,
            system="You are an expert Text-to-SQL system. Return only a valid SQL query.",
            temperature=0.0,
        )
        return self._extract_sql(response)

    def _choose_candidate(self, question, options):
        if not options:
            return ""

        if len(options) == 1:
            return options[0]

        numbered = "\n".join(f"{i}: {sql}" for i, sql in enumerate(options))
        prompt = (
            "Select the best SQL query for the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Candidates:\n{numbered}\n\n"
            "Return only the zero-based index of the best candidate."
        )

        response = self._llm_text(
            prompt,
            system="You are a precise SQL evaluator. Return only an integer index.",
            temperature=0.0,
        )

        text = (response or "").strip()
        digit_groups = "".join(ch if ch.isdigit() else " " for ch in text).split()

        if digit_groups:
            try:
                idx = int(digit_groups[0])
                if 0 <= idx < len(options):
                    return options[idx]
            except Exception:
                pass

        extracted = self._extract_sql(response)
        normalized_extracted = self._normalize(extracted)

        for option in options:
            if self._normalize(option) == normalized_extracted:
                return option

        for option in options:
            if option.strip() and option.strip() in text:
                return option

        return ""

    def _llm_text(self, prompt, system="", temperature=0.0, n=1):
        try:
            output = self.llm(prompt, system=system, temperature=temperature, n=n)
        except TypeError:
            try:
                output = self.llm(prompt)
            except Exception:
                return ""
        except Exception:
            return ""

        if isinstance(output, list):
            output = output[0] if output else ""

        if not isinstance(output, str):
            output = str(output)

        return output

    def _extract_sql(self, text):
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if sql:
            return str(sql).strip()

        return str(text).strip()

    def _normalize(self, sql):
        return " ".join(str(sql or "").split()).lower().strip()

    def _result_signature(self, rows):
        if rows is None:
            return "None"

        if isinstance(rows, list):
            try:
                return repr(sorted(str(row) for row in rows))
            except Exception:
                return repr([str(row) for row in rows])

        return repr(rows)