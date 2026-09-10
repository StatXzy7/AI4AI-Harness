"""Adaptive self-consistency for GSM8K: a greedy anchor plus escalating batches of diversely nudged sampled solutions are plurality-voted, with an LLM arbiter to break ties and a strict short-answer retry as the last-resort fallback."""

import math