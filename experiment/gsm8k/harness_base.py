"""Math-harness base class: the GSM8K twin of TTHE's SQLHarness.

A harness is ARBITRARY PYTHON wrapping the FROZEN solver (bridge.solver_llm).
Same two invariants as the SQL side:

  * FROZEN SOLVER -- no new client, no endpoint changes; you may change HOW you
    call it (prompt, temperature, number of calls, voting, self-checks).
  * LABEL-FREE -- the harness never sees the gold answer; correctness is
    measured outside solve(), by numeric comparison.

Available signals INSIDE solve(): the question text, the model's own chain-of-
thought/answer text, and any self-checks the harness invents (e.g. re-asking,
voting, verification prompts). There is no executor -- "execution feedback" in
this domain is whatever the harness can derive from the model's own output.
"""
from abc import ABC, abstractmethod

import sys
from pathlib import Path

_TTHE = Path(__file__).resolve().parents[2] / "external" / "TTHE"
if str(_TTHE) not in sys.path:
    sys.path.insert(0, str(_TTHE))

from text_to_sql import bridge            # noqa: E402  (solver client + cache)


class MathHarness(ABC):
    """Subclass this. solve() must return the final answer as a string.

    Helpers (use or ignore):
        self.llm(prompt, system="", temperature=0.0, n=1)
            the frozen solver; n=1 -> str, n>1 -> list[str]
        self.trace                       every model call, in order
    """

    def __init__(self):
        self._trace = []
        self._call_seq = {}

    def llm(self, prompt, system="", temperature=0.0, n=1):
        sig = (prompt, system, temperature, n)
        seq = self._call_seq.get(sig, 0)
        self._call_seq[sig] = seq + 1
        out = bridge.solver_llm(prompt, system=system, temperature=temperature, n=n, seq=seq)
        self._trace.append({"step": "solver_llm", "system": system, "prompt": prompt[:2000],
                            "response": out if isinstance(out, str) else list(out)})
        return out

    @abstractmethod
    def solve(self, question: str) -> str:
        ...
