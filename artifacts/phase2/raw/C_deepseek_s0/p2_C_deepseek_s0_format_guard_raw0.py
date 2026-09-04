"""A text-to-SQL harness that enforces a single fenced SQL output by validating the response format in a retry loop before returning the extracted query."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0FormatGuard(SQLHarness):
    _FENCE_RE = re.compile(
        r"^\s*