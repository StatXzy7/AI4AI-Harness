"""Repair-loop harness: execute candidate SQL and feed errors back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS1G3(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: standard single-shot generation.
        base_prompt = (
            f"You are a Text-to-SQL expert.\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a single SQLite-compatible SQL query that answers the question. "
            f"Return ONLY the SQL, no prose, no markdown fences."
        )

        messages = [
            {"role": "system", "content": "You translate natural-language questions into precise SQL."},
            {"role": "user", "content": base_prompt},
        ]

        final_sql = ""
        max_attempts = 3

        for attempt in range(max_attempts):
            # Use the last user message as the prompt; pass full message list as context implicitly
            # by re-asking with the most recent instruction (the conversation is rebuilt each iteration).
            prompt_for_call = messages[-1]["content"] if attempt == 0 else repair_prompt
            raw = self.llm(
                prompt_for_call,
                system=messages[0]["content"],
                temperature=0.0,
                n=1,
            )
            candidate = bridge.extract_sql(raw).strip()
            if not candidate:
                candidate = raw.strip()

            # Try to execute the candidate.
            result = self.execute(candidate)
            if result.get("ok"):
                final_sql = candidate
                break

            # Execution failed: append the failure context and ask the LLM to repair.
            err = result.get("error", "unknown error")
            messages.append({"role": "assistant", "content": candidate})
            messages.append({
                "role": "user",
                "content": (
                    f"The SQL you produced failed to execute with this error:\n{err}\n\n"
                    f"Question (restated): {question}\n"
                    f"Database schema:\n{self.schema}\n\n"
                    f"Produce a corrected SQL query. Return ONLY the SQL, no prose, no markdown fences."
                ),
            })
            repair_prompt = messages[-1]["content"]
        else:
            # If all attempts failed, keep the last candidate as best effort.
            final_sql = candidate if 'candidate' in locals() else ""

        return final_sql