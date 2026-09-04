"""First links a question to relevant schema DDL, then writes SQL against only that linked subset."""
from __future__ import annotations

import re
from typing import Any

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        linked_schema = self._link_schema(question)
        sql_raw = self._generate_sql(question, linked_schema)
        return bridge.extract_sql(sql_raw)

    def _link_schema(self, question: str) -> str:
        prompt = (
            "You are a database schema linker. Given a question and the full database schema, "
            "produce a minimal linked schema containing only the tables and columns needed to answer the question.\n"
            "If a table is relevant but only some of its columns are relevant, include only those columns.\n"
            "Preserve the original schema format exactly.\n"
            "Do not include any explanation, markdown, or code fences; output only the linked schema.\n\n"
            f"### DATABASE SCHEMA ###\n{self.schema}\n\n"
            f"### QUESTION ###\n{question}\n\n"
            "### LINKED SCHEMA ###"
        )
        raw = self.llm(
            prompt,
            system="You are a precise database schema linker.",
            temperature=0.0,
            n=1,
        )
        return self._strip_code_fences(self._as_text(raw))

    def _generate_sql(self, question: str, linked_schema: str) -> str:
        prompt = (
            "Write a single SQL query that answers the question.\n"
            "Use only the linked schema below; do not reference any other tables or columns.\n\n"
            f"### LINKED SCHEMA ###\n{linked_schema}\n\n"
            f"### QUESTION ###\n{question}\n\n"
            "### SQL ###"
        )
        raw = self.llm(
            prompt,
            system="You are a SQL expert. Output only SQL.",
            temperature=0.0,
            n=1,
        )
        return self._as_text(raw)

    @staticmethod
    def _as_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        if response is None:
            return ""
        if hasattr(response, "text"):
            return response.text

        choices = getattr(response, "choices", None)
        if choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    return message.get("content", "")
                return first.get("text", "")

            message = getattr(first, "message", None)
            if message is not None:
                return getattr(message, "content", "") or ""
            return getattr(first, "text", "") or str(first)

        return str(response)

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        match = re.search(
            r"