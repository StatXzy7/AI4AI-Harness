"""P2P2DMinimaxS0FormatGuard wraps a weak text-to-SQL solver with strict output formatting, schema validation, and fence-enforced SQL extraction to guarantee executable, well-formed queries."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0FormatGuard(SQLHarness):
    """Format-guarded harness that enforces