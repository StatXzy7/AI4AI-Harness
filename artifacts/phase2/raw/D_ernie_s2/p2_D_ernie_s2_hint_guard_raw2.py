"""This harness parses a 'Hint:' line from the question and restates its constraints as hard requirements in the prompt before generating SQL."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Parse the hint line from the question
        lines = question.split('\n')
        hint_text = ""
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Hint:"):
                hint_text = stripped[len("Hint:"):].strip()
            else:
                filtered_lines.append(line)
        question_without_hint = '\n'.join(filtered_lines).strip()
        
        # Construct the prompt with hard requirements if hint exists
        if hint_text:
            hard_req = f"Hard requirements from hint: {hint_text}"
        else:
            hard_req = ""
        
        prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question_without_hint}\n\n"
            f"{hard_req}\n\n"
            f"Write a SQL query that answers the question and satisfies the hard requirements. "
            f"Only output the SQL query."
        )
        
        # Generate SQL using the LLM
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        return sql