"""Generate an initial answer, verify it with a second pass, and adjudicate disagreements to select a compact final answer."""
from ..harness_base import MathHarness
import re


class GsmGsmQwenS0G2(MathHarness):
    def solve(self, question: str) -> str:
        system = self._system()
        candidates = {}

        def add_candidate(raw, weight):
            clean = self._clean_answer(raw)
            canon = self._canonical(raw)
            if not canon:
                return
            entry = candidates.get(canon)
            if entry is None:
                candidates[canon] = {"count": 1, "weight": float(weight), "display": clean}
            else:
                entry["count"] += 1
                entry["weight"] += float(weight)
                if self._prefer_display(clean, entry["display"]):
                    entry["display"] = clean

        first = self._generate(self._initial_prompt(question), system)
        add_candidate(first, 1.0)

        proposed = self._clean_answer(first) or "None"
        second = self._generate(self._verification_prompt(question, proposed), system)
        add_candidate(second, 1.2)

        if not candidates:
            last = self._generate(self._last_resort_prompt(question), system)
            add_candidate(last, 0.8)

        if len(candidates) > 1:
            top = sorted(
                candidates.items(),
                key=lambda item: (item[1]["count"], item[1]["weight"]),
                reverse=True,
            )[:5]
            displays = [item[1]["display"] for item in top if item[1]["display"]]
            if displays:
                judge = self._generate(self._judge_prompt(question, displays), system)
                judge_canon = self._canonical(judge)
                if judge_canon:
                    if judge_canon in candidates:
                        add_candidate(judge, 3.0)
                    else:
                        add_candidate(judge, 1.5)

        if not candidates:
            return ""

        best = max(
            candidates.values(),
            key=lambda v: (v["count"], v["weight"], -len(v["display"])),
        )
        return self._clean_answer(best["display"]) or best["display"]

    def _generate(self, prompt, system):
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        return self._to_text(out)

    def _to_text(self, out):
        if out is None:
            return ""
        if isinstance(out, str):
            return out
        if isinstance(out, (list, tuple)):
            return self._to_text(out[0]) if out else ""
        if isinstance(out, dict):
            for key in ("text", "completion", "output", "response", "content"):
                if key in out:
                    return self._to_text(out[key])
        return str(out)

    def _system(self):
        return (
            r"You are a careful competition-math solver. "
            "Put the final answer on the last line exactly as:\n"
            "#### <answer>\n"
            r"The answer must be compact and exact: e.g. 42, 3/4, \frac{3}{4}, 2\sqrt{3}, (3,4], (2,5). "
            "Do not include units or prose in the final answer."
        )

    def _initial_prompt(self, question):
        return (
            "Solve the problem step by step. Be careful about domains, signs, endpoint inclusion, "
            "and extraneous solutions.\n\n"
            f"Problem:\n{question}\n\n"
            "End your response with the final answer on the last line in the form:\n"
            "#### <answer>"
        )

    def _verification_prompt(self, question, proposed):
        return (
            "A previous solver gave a proposed answer. Independently solve the problem, then verify or correct the proposal.\n"
            "Check by substitution, boundary cases, parity, estimation, or an alternate method when possible.\n\n"
            f"Problem:\n{question}\n\n"
            f"Proposed answer: {proposed}\n\n"
            "If the proposed answer is incorrect, give the corrected answer.\n"
            "End your response with the final answer on the last line in the form:\n"
            "#### <answer>"
        )

    def _judge_prompt(self, question, candidate_answers):
        rendered = "\n".join(f"{i}. {ans}" for i, ans in enumerate(candidate_answers, 1))
        return (
            "Different candidate final answers were produced. Determine the correct final answer.\n"
            "Verify the candidates by solving the problem or checking with an independent method.\n\n"
            f"Problem:\n{question}\n\n"
            f"Candidate answers:\n{rendered}\n\n"
            "Choose the correct answer, or provide a corrected answer if all candidates are wrong.\n"
            "End your response with the final answer on the last line in the form:\n"
            "#### <answer>"
        )

    def _last_resort_prompt(self, question):
        return (
            "Give only the final answer to the problem. Do not show work.\n\n"
            f"Problem:\n{question}\n\n"
            "End with:\n"
            "#### <answer>"
        )

    def _clean_answer(self, text):
        if text is None:
            return ""
        s = str(text)
        s = s.replace("