"""Generates multiple prompted candidate solutions, extracts normalized answers, and selects by majority vote with an LLM adjudicator."""
import re
from math import gcd

try:
    from ..harness_base import MathHarness
except Exception:
    try:
        from harness_base import MathHarness
    except Exception:
        class MathHarness:
            def llm(self, prompt, system="", temperature=0.0, n=1):
                raise NotImplementedError


class GsmGsmQwenS0G4(MathHarness):
    _SYSTEM = (
        "You are an expert competition-math solver. "
        "Put your final answer on the last line exactly as '#### <answer>'. "
        "The answer may be a plain number, fraction, LaTeX expression, interval, or tuple. "
        "Examples: #### 42, #### \\frac{3}{4}, #### (3,4]."
    )

    _JUDGE_SYSTEM = (
        "You are a careful competition-math judge. "
        "Determine the correct final answer. "
        "Put your final answer on the last line exactly as '#### <answer>'."
    )

    def solve(self, question: str) -> str:
        q = (question or "").strip()
        candidates = []

        for prompt in self._candidate_prompts(q):
            out = self._call_llm(prompt, self._SYSTEM)
            ans = self._extract_answer(out)
            if ans:
                candidates.append((self._norm(ans), ans))

        if not candidates:
            return ""

        counts = {}
        for norm, _ in candidates:
            counts[norm] = counts.get(norm, 0) + 1

        best_count = max(counts.values())
        if best_count >= 2:
            best_norms = [norm for norm, cnt in counts.items() if cnt == best_count]
            best_norm = min(best_norms, key=lambda x: (len(x), x))
            matching = [ans for norm, ans in candidates if norm == best_norm]
            return min(matching, key=lambda x: (len(x), x))

        judge_prompt = self._judge_prompt(q, [ans for _, ans in candidates])
        out = self._call_llm(judge_prompt, self._JUDGE_SYSTEM)
        judged = self._extract_answer(out)

        if judged:
            jnorm = self._norm(judged)
            matching = [ans for norm, ans in candidates if norm == jnorm]
            if matching:
                return min(matching, key=lambda x: (len(x), x))
            return judged

        return min((ans for _, ans in candidates), key=lambda x: (len(x), x))

    def _candidate_prompts(self, question: str):
        final = "Put your final answer on the last line exactly as '#### <answer>'."
        return [
            f"Problem:\n{question}\n\nSolve the problem step by step. {final}",
            f"Problem:\n{question}\n\nSolve the problem independently and concisely. {final}",
            f"Problem:\n{question}\n\nSolve carefully, then check the result against the problem constraints. {final}",
        ]

    def _judge_prompt(self, question: str, answers):
        lines = "\n".join(f"{i + 1}. {ans}" for i, ans in enumerate(answers))
        return (
            f"Problem:\n{question}\n\nCandidate final answers:\n{lines}\n\n"
            "Determine the correct final answer. Solve independently if needed and check the candidates. "
            "Put your final answer on the last line exactly as '#### <answer>'."
        )

    def _call_llm(self, prompt: str, system: str) -> str:
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                out = self.llm(prompt, system, 0.0, 1)
            except Exception:
                out = ""
        except Exception:
            out = ""

        if out is None:
            return ""
        return out if isinstance(out, str) else str(out)

    def _extract_answer(self, text: str) -> str:
        if not text:
            return ""
        text = str(text)

        ans = self._extract_hash_answer(text)
        if ans:
            return self._compact(ans)

        ans = self._extract_boxed(text)
        if ans:
            return self._compact(ans)

        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            m = re.search(r"(?:final\s*answer|answer)\s*[:\-]?\s*(.+)$", line, re.I)
            if m:
                return self._compact(m.group(1))

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            return self._compact(lines[-1])

        return ""

    def _extract_hash_answer(self, text: str) -> str:
        matches = re.findall(r"####\s*(.*)", text)
        for match in reversed(matches):
            if match.strip():
                return match.strip()
        return ""

    def _extract_boxed(self, text: str) -> str:
        if not text:
            return ""

        results = []
        pos = 0

        while True:
            idx = text.find("\\boxed", pos)
            if idx == -1:
                break

            brace = text.find("{", idx)
            if brace == -1:
                break

            depth = 0
            end = -1

            for j in range(brace, len(text)):
                ch = text[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break

            if end == -1:
                break

            results.append(text[brace + 1:end])
            pos = end + 1

        if not results:
            return ""
        return results[-1].strip()

    def _compact(self, ans: str) -> str:
        if ans is None:
            return ""

        ans = str(ans).strip()
        if not ans:
            return ""

        if ans.startswith("