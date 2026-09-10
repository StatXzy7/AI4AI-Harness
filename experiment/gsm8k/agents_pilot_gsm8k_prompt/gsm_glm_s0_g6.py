"""Adaptive self-consistency harness: sample several chain-of-thought solutions at nonzero temperature, extract and majority-vote their final numeric answers (weighting well-formatted '####' replies higher and anchoring ties to a greedy decode), and stop sampling early once one answer has a decisive lead."""

import re

from ..harness_base import MathHarness


class GsmGsmGlmS0G6(MathHarness):
    """Improves on a single greedy call via adaptive self-consistency voting.

    Control flow inside ``solve``:

    1. **Greedy anchor.** One temperature-0 solution is generated first; it is
       the model's single most likely solution path.
    2. **Diverse sampling.** Additional solutions are drawn at nonzero
       temperature, batched through the solver's ``n`` argument when possible
       and one-by-one otherwise.
    3. **Weighted vote.** Each reply's final answer is extracted with a
       cascade of parsers (``#### x``  >  "answer is x"  >  last number) and
       cast as a vote: replies that used the explicit GSM8K ``####`` marker
       count fully, heuristic parses count half, and the greedy anchor gets a
       small prior (and, being registered first, wins exact ties).
    4. **Early stopping.** Sampling halts as soon as the leading answer's
       weighted margin is decisive; otherwise the full budget is spent and the
       plurality answer wins.

    No code execution or external tools are used -- the only signals are the
    question and the solver's own text output.
    """

    # ---- hyperparameters of the voting scheme -------------------------
    sample_temperature = 0.7   # diversity for the voting pool
    sample_batch = 2           # samples requested per round (via `n` when possible)
    min_samples = 4            # samples required before early stopping is allowed
    max_samples = 8            # hard budget on sampled solutions
    early_stop_margin = 2.0    # weighted-vote lead that ends sampling early
    anchor_weight = 1.5        # prior granted to the greedy (temperature-0) answer

    system_prompt = (
        "You are a careful grade-school math tutor. Work through the problem "
        "in short, explicit steps, double-check the arithmetic, and finish "
        "with a final line of exactly the form '#### <number>' where <number> "
        "is the final numeric answer."
    )

    user_template = (
        "Problem:\n{question}\n\n"
        "Solve it step by step, then give the final numeric answer on the "
        "last line in the form '#### <number>'."
    )

    # ---- answer-extraction patterns ------------------------------------
    _hash_re = re.compile(r"####\s*([^\n]+)")
    _answer_re = re.compile(
        r"(?:final\s+answer|answer)\s*(?:is|:|=|should\s+be)?\s*\$?\s*"
        r"(-?[\d,]*\d(?:\.\d+)?)",
        re.IGNORECASE,
    )
    _number_re = re.compile(r"-?(?:\d[\d,]*(?:\.\d+)?|\.\d+)")

    # ------------------------------------------------------------------ #
    # Low-level plumbing: talking to the frozen solver                    #
    # ------------------------------------------------------------------ #

    def _prompt(self, question: str) -> str:
        return self.user_template.format(question=question)

    def _call(self, question: str, temperature: float, n: int):
        """Invoke the frozen solver, tolerating signature/output variations."""
        prompt = self._prompt(question)
        try:
            return self.llm(
                prompt, system=self.system_prompt, temperature=temperature, n=n
            )
        except TypeError:
            # Solver variant without an `n` parameter.
            try:
                return self.llm(
                    prompt, system=self.system_prompt, temperature=temperature
                )
            except Exception:
                return ""
        except Exception:
            # A failed call should not kill the whole vote; it just yields
            # no text (and hence no vote) for that sample.
            return ""

    @staticmethod
    def _as_text(out) -> str:
        """Coerce a solver reply of unknown shape into plain text."""
        if out is None:
            return ""
        if isinstance(out, str):
            return out
        if isinstance(out, (list, tuple)):
            return "\n".join(GsmGsmGlmS0G6._as_text(item) for item in out)
        if isinstance(out, dict):
            for key in ("text", "content", "response", "output", "completion"):
                value = out.get(key)
                if isinstance(value, str):
                    return value
            return "\n".join(GsmGsmGlmS0G6._as_text(v) for v in out.values())
        for attr in ("text", "content", "output", "completion"):
            value = getattr(out, attr, None)
            if isinstance(value, str):
                return value
        return str(out)

    def _as_texts(self, out):
        """Split a (possibly multi-completion) reply into a list of texts."""
        if isinstance(out, (list, tuple)):
            return [self._as_text(item) for item in out]
        text = self._as_text(out)
        return [text] if text else []

    def _sample(self, question: str, k: int, temperature: float):
        """Return exactly ``k`` sampled solution texts."""
        texts = []
        if k > 1:
            # Try a single batched call first; top up one-by-one if the
            # solver does not actually return k completions.
            texts = self._as_texts(self._call(question, temperature, k))
        while len(texts) < k:
            texts.append(self._as_text(self._call(question, temperature, 1)))
        return texts[:k]

    # ------------------------------------------------------------------ #
    # Answer extraction and normalisation                                 #
    # ------------------------------------------------------------------ #

    @classmethod
    def _extract(cls, text: str):
        """Return ``(canonical_answer, used_explicit_marker)``."""
        if text:
            hits = cls._hash_re.findall(text)      # GSM8K-style "#### 42"
            if hits:
                return cls._normalize(hits[-1]), True
            hits = cls._answer_re.findall(text)    # "The answer is 42"
            if hits:
                return cls._normalize(hits[-1]), False
            hits = cls._number_re.findall(text)    # last number in the reply
            if hits:
                return cls._normalize(hits[-1]), False
        return None, False

    @classmethod
    def _normalize(cls, raw):
        """Canonicalise '$1,234.50' / '42.' / ' 42 ' -> '1234.5' / '42'."""
        if raw is None:
            return None
        match = cls._number_re.search(str(raw))
        if not match:
            return None
        token = match.group(0).replace(",", "")
        try:
            value = float(token)
        except ValueError:
            return None
        if value == int(value):
            return str(int(value))
        trimmed = ("%.10f" % value).rstrip("0").rstrip(".")
        return trimmed if trimmed not in ("", "-") else "0"

    # ------------------------------------------------------------------ #
    # Main control flow                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rank(tally, order):
        """Deterministic ranking: weight first, then first-seen order."""
        return sorted(tally.items(), key=lambda kv: (-kv[1], order[kv[0]]))

    def solve(self, question: str) -> str:
        # ---- Stage 1: greedy anchor (single most likely solution path) --
        anchor_text = self._as_text(self._call(question, 0.0, 1))
        anchor_ans, _ = self._extract(anchor_text)

        tally = {}   # canonical answer -> weighted vote total
        order = {}   # canonical answer -> insertion index (tie-breaking)

        def add_vote(answer, weight):
            if answer is None:
                return
            if answer not in tally:
                tally[answer] = 0.0
                order[answer] = len(order)
            tally[answer] += weight

        # The greedy answer seeds the vote with a small prior and, being
        # registered first, wins any exact tie.
        add_vote(anchor_ans, self.anchor_weight)

        # ---- Stage 2: adaptive self-consistency sampling ----------------
        drawn = 0
        while drawn < self.max_samples:
            k = min(self.sample_batch, self.max_samples - drawn)
            for text in self._sample(question, k, self.sample_temperature):
                drawn += 1
                answer, marked = self._extract(text)
                # Explicit "####" answers are on-policy and parse reliably,
                # so they count fully; heuristic parses count half.
                add_vote(answer, 1.0 if marked else 0.5)

            # Early stopping: quit while ahead once enough evidence is in.
            if drawn >= self.min_samples and tally:
                ranked = self._rank(tally, order)
                runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
                if ranked[0][1] - runner_up >= self.early_stop_margin:
                    break

        # ---- Decision: plurality (weight, then anchor-first tie-break) --
        if tally:
            return self._rank(tally, order)[0][0]

        # Last resort: nothing parsed anywhere; echo the anchor's last line.
        lines = [ln.strip() for ln in anchor_text.splitlines() if ln.strip()]
        return lines[-1] if lines else ""


__all__ = ["GsmGsmGlmS0G6"]