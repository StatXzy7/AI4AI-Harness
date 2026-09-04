"""Repair loop: a greedy SQL draft is executed against the database and every execution error is fed back to the LLM for up to three corrective regenerations."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge

_FENCE_RE = re.compile(r"