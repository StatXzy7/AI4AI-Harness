"""Format-guarded harness that forces a fenced SQL answer and repairs schema or execution errors."""
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2CQwenS0FormatGuard(SQLHarness):
    MAX_ATTEMPTS = 3

    _SYSTEM = (
        "You are a precise Text-to-SQL engine. "
        "Your entire reply must be exactly one SQL statement inside a single