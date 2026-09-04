"""Execution-grounded voting: draw a greedy anchor plus temperature-perturbed samples from the frozen solver, execute every read-only candidate, and return the SQL whose result wins the consensus vote."""
# MECHANISM: vote

import hashlib
import re
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G1(SQLHarness):
    """Self-consistency voting over the frozen Text-to-SQL solver.

    Instead of trusting a single greedy generation, ``solve`` runs a small
    ensemble per question:

    1. Draw a candidate pool: one greedy anchor (temperature 0.0) plus
       ``N_SAMPLES`` perturbed samples at higher temperatures.
    2. Execute each *unique, read-only* candidate against the database.
    3. Bucket executable candidates by a fingerprint of their result rows
       and weight each bucket by the number of samples that produced it.
    4. Return the most frequent SQL inside the bucket with the strongest
       consensus; if nothing executes cleanly, fall back to a plain
       frequency vote over the candidate texts.

    Execution is used only to validate and bucket candidates -- error
    messages are never fed back into a prompt