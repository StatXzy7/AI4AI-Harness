"""Two-stage harness: first stage produces skeleton/draft SQL, second stage refines with execution feedback."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: generate a skeleton query with high temperature to get diverse approach
        skeleton_prompt = (
            f"Given the schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Produce a SQL skeleton with the main FROM/JOIN/WHERE structure filled in. "
            "Use placeholders like <COL> or <EXPR> where you're unsure. Output ONLY the skeleton SQL."
        )
        skeleton_text = self.llm(skeleton_prompt, system="You draft SQL skeletons.", temperature=0.4, n=1)
        skeleton_sql = bridge.extract_sql(skeleton_text) or skeleton_text.strip()

        # Stage 2: refine the skeleton into a final query, using skeleton as guidance
        refine_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Draft skeleton:\n{skeleton_sql}\n\n"
            "Refine the skeleton into a complete, correct SQL query. "
            "Replace any placeholders with the appropriate columns or expressions. "
            "Output ONLY the final SQL."
        )
        refined_text = self.llm(refine_prompt, system="You produce executable SQL.", temperature=0.0, n=1)
        candidate = bridge.extract_sql(refined_text) or refined_text.strip()

        # Optional repair: if execution fails, retry once with error feedback
        result = self.execute(candidate)
        if not result["ok"]:
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Failed SQL:\n{candidate}\n\n"
                f"Execution error:\n{result.get('error', '')}\n\n"
                "Fix the error and output ONLY the corrected SQL."
            )
            repaired_text = self.llm(repair_prompt, system="You repair SQL.", temperature=0.0, n=1)
            candidate = bridge.extract_sql(repaired_text) or candidate

        return candidate