"""A harness that wraps a frozen weak solver for Text-to-SQL by enforcing strict output formatting and schema fidelity through prompt engineering and a single extraction-execution cycle."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Construct a prompt that heavily emphasizes format and schema constraints
        prompt = f"""You are a Text-to-SQL solver. Generate a SQL query that answers the question.

Database Schema:
{self.schema}

Question: {question}

CRITICAL INSTRUCTIONS:
1. Use ONLY the table and column names exactly as provided in the schema. Do not invent or modify names.
2. Your final answer MUST be inside a