"""Decomposes the question into an ordered chain of sub-questions, answers each sub-question with its own small frozen-solver call, and then assembles the per-step SQL into one final query."""

import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS2Decompose"]


class P2P2CGlmS2Decompose(SQLHarness):
    """Prompt-to-prompt decomposition harness: plan sub-questions -> solve each -> assemble."""

    MAX_STEPS = 5          # upper bound on sub-questions emitted by the planner
    REPAIR_ATTEMPTS = 1    # execution-driven repair rounds for the assembled SQL
    HISTORY_WINDOW = 3     # earlier sub-answers echoed into later step prompts

    _ENUM_RE = re.compile(r"^\s*(?:\d{1,2}\s*[).:\-]|[-*•])\s*(.+?)\s*$")
    _PREAMBLE_RE = re.compile(
        r"^(here\s+(is|are)|sure|certainly|of\s+course|below|the\s+sub)", re.I
    )

    DECOMPOSE_SYSTEM = (
        "You decompose Text-to-SQL questions. "
        "Reply with a numbered list of sub-questions and nothing else."
    )
    STEP_SYSTEM = (
        "You are an expert SQLite writer. "
        "Reply with a single SQL query inside one