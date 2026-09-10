"""Wraps a frozen LLM solver with self-consistency voting: sample multiple solutions at temperature>0, parse each, and return the majority final answer."""
from collections import Counter
from ..harness_base import MathHarness

PROMPT_TEMPLATE = (
    "Solve the following math problem step by step. Put your final answer on "
    "the last line, exactly in the form '#### <answer>'. The answer should be "
    "compact: a plain number, a fraction like \\frac{{a}}{{b}} or a/b, a "
    "LaTeX expression, an interval like (a,b], or a tuple like (a,b).\n\n"
    "Problem:\n{question}\n\n"
    "Solution:"
)

ANSWER_KEY = "####"


def _extract_final_answer(text: str) -> str | None:
    """Pull the substring after the LAST '####' marker on the last non-empty line."""
    # Look for the marker; the harness expects it on the very last line.
    if ANSWER_KEY not in text:
        return None
    # Take everything after the last occurrence of the marker.
    idx = text.rfind(ANSWER_KEY)
    after = text[idx + len(ANSWER_KEY):]
    # Strip leading separators like ':' or whitespace.
    after = after.lstrip(": \t\r\n")
    # The answer is the first token-ish chunk on what follows.
    # Split off at a newline in case extra text was appended.
    if "\n" in after:
        after = after.split("\n", 1)[0]
    after = after.strip()
    return after or None


def _normalize(ans: str) -> str:
    """Light normalization so '3/4', '\\frac{3}{4}', ' 3 / 4 ' collapse together."""
    s = ans.strip()
    # Unify LaTeX fraction notation to a/b for comparison purposes.
    if s.startswith("\\frac{") and s.endswith("}"):
        # \frac{a}{b}  ->  a/b
        inner = s[len("\\frac{") : -1]
        # split at the last "}{"
        if "}{" in inner:
            a, b = inner.rsplit("}{", 1)
            s = f"{a}/{b}"
    # Collapse whitespace around '/'.
    s = s.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
    # Remove stray spaces.
    s = s.replace(" ", "")
    return s


class GsmGsmMinimaxS0G4(MathHarness):
    # Tunables for the self-consistency loop.
    N_SAMPLES = 5
    TEMPERATURE = 0.6
    SYSTEM = (
        "You are a careful math solver. Always end your response with a final "
        "line of the form '#### <answer>' containing only the compact answer."
    )

    def solve(self, question: str) -> str:
        prompt = PROMPT_TEMPLATE.format(question=question.strip())

        # 1) Fan out: generate N independent candidate solutions.
        try:
            completions = self.llm(
                prompt,
                system=self.SYSTEM,
                temperature=self.TEMPERATURE,
                n=self.N_SAMPLES,
            )
        except TypeError:
            # Fallback if the underlying client doesn't accept `n`.
            completions = [self.llm(prompt, system=self.SYSTEM,
                                    temperature=self.TEMPERATURE)]

        # 2) Parse each completion to its final answer.
        parsed = []
        for comp in completions:
            ans = _extract_final_answer(comp)
            if ans is not None:
                parsed.append(ans)

        if not parsed:
            # Parsing failed on every sample: fall back to a greedy T=0 call.
            fallback = self.llm(prompt, system=self.SYSTEM,
                                temperature=0.0, n=1)
            ans = _extract_final_answer(fallback)
            return ans if ans is not None else fallback.strip()

        # 3) Self-consistency: majority vote over normalized answers,
        #    breaking ties by preferring the first occurrence (which tends to
        #    be the more "central" sample at moderate temperature).
        normalized = [_normalize(a) for a in parsed]
        counts = Counter(normalized)
        _top_norm, top_count = counts.most_common(1)[0]
        # Collect candidates tied at the top.
        tied = [a for a, n in zip(parsed, normalized) if n == _top_norm]

        # Pick the tied answer that appears earliest (stable tie-break).
        winner_norm = _top_norm
        winner = next(a for a, n in zip(parsed, normalized)
                      if n == winner_norm)

        # 4) Sanity check: if the top answer appears only once across N
        #    samples, the model is uncertain -- re-run greedy at T=0 and
        #    accept it only if it agrees with the plurality; otherwise trust
        #    the plurality (self-consistency literature).
        if top_count == 1 and self.N_SAMPLES > 1:
            greedy = self.llm(prompt, system=self.SYSTEM,
                              temperature=0.0, n=1)
            greedy_ans = _extract_final_answer(greedy)
            if greedy_ans is not None:
                if _normalize(greedy_ans) == winner_norm:
                    return greedy_ans
                # Disagreement under full uncertainty: keep plurality.
        return winner