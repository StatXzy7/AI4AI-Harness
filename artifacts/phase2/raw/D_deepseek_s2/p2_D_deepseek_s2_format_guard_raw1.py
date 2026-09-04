"""A format-guard harness that requires fenced SQL output, extracts the query, and retries on missing fences or execution errors."""
import re
from ..harness_base import SQLHarness
from .. import bridge

_FENCE_PATTERN = re.compile(r"