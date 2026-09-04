"""Ask the LLM for three SQL attempts and return the SQL whose result rows have majority support."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. Return only the SQL."
        )

        responses = self.llm(prompt, system="", temperature=0.7, n=3)

        if isinstance(responses, str):
            response_list = [responses]
        elif responses is None:
            response_list = []
        else:
            try:
                response_list = list(responses)
            except TypeError:
                response_list = [responses]

        parsed_sqls = []
        executed = []

        for response in response_list:
            if not isinstance(response, str):
                continue

            sql = bridge.extract_sql(response)
            if not sql:
                continue

            parsed_sqls.append(sql)

            try:
                result = self.execute(sql)
            except Exception:
                continue

            if result and result.get("ok"):
                executed.append((sql, result.get("rows")))

        if not executed:
            return parsed_sqls[0] if parsed_sqls else ""

        votes = []
        for sql, rows in executed:
            for vote in votes:
                if vote["rows"] == rows:
                    vote["count"] += 1
                    if sql not in vote["sqls"]:
                        vote["sqls"].append(sql)
                    break
            else:
                votes.append({"rows": rows, "count": 1, "sqls": [sql]})

        for vote in votes:
            if vote["count"] >= 2:
                return vote["sqls"][0]

        return executed[0][0]