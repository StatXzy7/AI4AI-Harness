"""Wraps a frozen weak Text-to-SQL solver with strict output-format guarding and schema fidelity enforcement."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2FormatGuard(SQLHarness):
    """Persona 2 + Persona 2C: a format-guard harness that emphasizes output format
    and schema fidelity, requiring the final answer inside a