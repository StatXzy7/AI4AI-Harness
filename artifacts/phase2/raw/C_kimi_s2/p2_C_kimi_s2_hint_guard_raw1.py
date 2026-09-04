"""Parse the question's 'Hint:' line into numbered hard requirements, inject them before SQL generation, and guard them with literal-presence checks plus execution-feedback retries."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2HintGuard(SQLHarness):
    """Hint-Guard Text-to-SQL harness.

    Mechanism (implemented in the control flow, not only the prompt):
      1. The 'Hint:' line is parsed out of the question with a regex.
      2. The hint is restated as a numbered list of HARD REQUIREMENTS placed
         *before* the SQL-writing instruction in every prompt.
      3. The model must restate each requirement and map it to a SQL construct
         before emitting its single