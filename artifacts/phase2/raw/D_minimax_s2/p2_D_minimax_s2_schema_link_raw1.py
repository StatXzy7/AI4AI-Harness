"""Two-pass harness that first links the question to relevant schema tables/columns, then writes SQL against only that linked subset."""
from ..harness_base import SQLHarness
from .. import bridge
import json
import re


class P2P2DMinimaxS2SchemaLink(SQLHarness):
    def _parse_linked_schema(self, raw: str) -> dict:
        """
        Try to extract a JSON object from the LLM's linked-schema response.
        Falls back to scanning for table/column mentions if JSON parsing fails.
        """
        # Attempt JSON extraction (handle