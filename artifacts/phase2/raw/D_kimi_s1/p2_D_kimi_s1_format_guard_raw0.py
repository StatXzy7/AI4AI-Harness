"""Format-guard harness that forces the frozen Text-to-SQL solver to emit exactly one schema-faithful fenced sql block and repairs failures through execution feedback in the control flow."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1FormatGuard(SQLHarness):
    """Strict output-format + schema-fidelity guard around the frozen weak solver.

    Control-flow strategy:
      1. Prompt with the schema and a hard format contract: exactly one