"""P2P2C Qwen S1 schema-linking harness that first identifies mentioned schema items and then generates SQL against that linked subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1SchemaLink(SQLHarness):
    """Schema-linking harness: link schema first, then generate SQL from the linked subset."""

    _JSON_FENCE_RE = re.compile(r"