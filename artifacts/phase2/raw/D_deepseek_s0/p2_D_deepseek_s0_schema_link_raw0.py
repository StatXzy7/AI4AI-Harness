"""First links the question to the relevant tables and columns, then generates SQL using only that linked schema subset."""
from ..harness_base import SQLHarness
from .. import bridge
import json


class P2P2DDeepseekS0SchemaLink(SQLHarness):
    """Schema-link first, then generate SQL from the linked schema subset."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _as_text(self, value):
        if isinstance(value, (list, tuple)):
            return str(value[0]) if value else ""
        return str(value or "")

    def _parse_json_object(self, text: str):
        if not text:
            return None
        text = text.strip()
        if text.startswith("