"""Self-consistency execution voting: draw one greedy plus several temperature-sampled SQL candidates, execute each distinct candidate once, and return the query whose execution-result fingerprint collects the most ballots, falling back to a plain text-frequency vote when nothing executes."""

# MECHANISM: vote

import hashlib
import json
import re
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge

_SYSTEM_PROMPT = (
    "You are an expert SQLite programmer. You always answer with exactly one "
    "valid SQLite SELECT statement and no commentary."
)

_PROMPT_TEMPLATE = """You are given a database schema and a natural-language question.

Database schema:
{schema}

Question: {question}

Write ONE SQLite query