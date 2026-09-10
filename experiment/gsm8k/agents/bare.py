"""Baseline harness: one greedy shot, question -> answer. No decomposition, no voting,
no self-checks. This is the floor every generated harness is measured against.
Mirrors the SQL-side bare.py convention (expert system prompt, one call, structured
final line)."""
from ..harness_base import MathHarness

SYS = ("You are an expert competition mathematician. Solve the problem carefully "
       "step by step, then output the final answer on the last line in the form "
       "#### <answer> (the answer may be a number, fraction, or LaTeX expression; "
       "nothing after it).")


class BareHarness(MathHarness):
    def solve(self, question: str) -> str:
        prompt = f"Question: {question}\n\nSolve the problem and end with '#### <final answer>'."
        resp = self.llm(prompt, system=SYS, temperature=0.0)
        return resp
