"""Harness that first links the question to relevant tables/columns and then generates SQL against that linked schema subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS1SchemaLink(SQLHarness):
    _IDENT = r'(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][\w$]*)'
    _CREATE_RE = re.compile(
        r"(?is)\bcreate\s+(?:temporary\s+|temp\s+)?(table|view)\s+"
        r"(?:if\s+not\s+exists\s+)?"
        r"(" + _IDENT + r")"
        r"(?:\s*\.\s*(" + _IDENT + r"))?"
    )
    _FENCE_RE = re.compile(r"