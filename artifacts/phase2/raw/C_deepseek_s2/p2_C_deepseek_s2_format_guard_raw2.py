"""Prompt a frozen solver to emit only a single fenced SQL block, enforce that format by strict parsing, and retry on format or execution errors."""

import re
from typing import List, Optional, Union

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2FormatGuard(SQLHarness):
    _MAX_ATTEMPTS = 3

    def solve(self, question: str) -> str:
        system = (
            "You are a text-to-SQL assistant. "
            "Your entire response must be exactly one code block with the `sql` language tag "
            "and no other text before or after it."
        )
        base_prompt = self._build_prompt(question)
        current_prompt = base_prompt
        last_text = ""

        for _ in range(self._MAX_ATTEMPTS):
            response = self.llm(current_prompt, system=system, temperature=0.0, n=1)
            last_text = self._as_text(response)

            strict_sql = self._extract_strict_fenced_sql(last_text)
            if strict_sql is None:
                current_prompt = self._append_feedback(
                    base_prompt,
                    "Your previous answer did not contain exactly one