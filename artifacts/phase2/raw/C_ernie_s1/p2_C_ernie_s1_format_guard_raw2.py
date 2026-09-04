"""Harness that enforces strict SQL output format and schema fidelity by extracting and validating SQL within code fences and checking table references against the schema."""

import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS1FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Generate a SQL query for the given question using the provided schema,
        ensuring the output is inside a