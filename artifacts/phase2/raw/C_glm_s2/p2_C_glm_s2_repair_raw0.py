"""Prompt-to-prompt-to-code harness: generate SQLite SQL from the schema and question, execute it, and on failure re-prompt the frozen solver with the failed query plus the exact SQLite error to regenerate, for up to 2 repair rounds."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS2Repair"]


class P2P2CGlmS2Repair(SQLHarness):
    """Generate -> execute -> repair loop wrapped around the frozen weak solver.

    The repair mechanism is enforced by the control flow of :meth:`solve`,
    not merely suggested inside the prompts:

    * attempt 1: initial generation from (schema, question)
    * every candidate is executed via ``self.execute`` immediately
    * on failure, the *exact* SQLite error string and the SQL that produced
      it are fed back into a new prompt, and the SQL is regenerated
    * this execute/repair cycle runs at most ``MAX_REPAIRS`` (= 2) times,
      i.e. at most 3 LLM calls in total
    * the first candidate that executes successfully is returned at once;
      if every attempt fails, the last candidate is returned as-is
    """

    MAX_REPAIRS = 2          # regenerations after the initial generation
    TEMPERATURE = 0.0        # deterministic decoding for every round

    SYSTEM = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, write exactly one SQL query that answers "
        "the question. Output only a single