"""Format-guarded harness enforcing strict SQL fence output for a frozen Text-to-SQL solver."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ..harness_base import SQLHarness
from .. import bridge


# Canonical prompt used to coerce the weak solver into emitting a strict fenced SQL answer.
_SYSTEM_PROMPT = (
    "You are a Text-to-SQL assistant. Convert the natural language question into a single "
    "valid SQL query that runs against the provided database schema. Output rules are strict "
    "and will be machine-validated: (1) emit exactly one fenced SQL code block delimited by "
    "triple-backticks with the language tag 'sql' (i.e.