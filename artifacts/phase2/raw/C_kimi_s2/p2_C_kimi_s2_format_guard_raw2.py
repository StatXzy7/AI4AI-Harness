"""Enforce a strict one-fenced-SQL-block output contract plus schema-fidelity checks in control flow, executing candidates and re-prompting the frozen solver with targeted format/schema/error feedback until a valid query survives."""

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CKimiS2FormatGuard"]


class P2P2CKimiS2FormatGuard(SQLHarness):
    """Format-and-schema guard around the frozen weak Text-to-SQL solver.

    The strategy lives in the control flow, not merely in the prompt:

    1. The prompt demands the final answer as exactly one