"""Decompose the question into ordered sub-questions, answer each with its own small LLM call that yields a partial SQL fragment, then assemble the fragments into the final execution-checked SQL."""

import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


_NUM_RE = re.compile(r"^(?:step\s*)?\d+\s*[.)\]:-]\s*(?P<sq>.+?)\s*$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[-*\u2022]\s*(?P<sq>.+?)\s*$")
_SQL_START_RE = re.compile(r"^(SELECT|WITH)\b", re.IGNORECASE)


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding