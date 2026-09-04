"""Enforces a strict fenced SQL output format, validates the query against the live schema, and retries with corrective prompts."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1FormatGuard(SQLHarness):
    _FENCE_RE = re.compile(r"\A\s*