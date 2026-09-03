"""Verify arXiv IDs used in references.bib via alphaxiv/arxiv landing checks (batch 1 results hand-verified)."""
import json
from pathlib import Path

# Batch-verified 2026-09-03 via alphaxiv/arxiv.org searches (see AUTO_REVIEW P1-11):
verified = {
    "2607.08124": "TTHE: Test-Time Harness Evolution",
    "2608.13951": "HELIX: Model-Harness Co-evolution for Recursive Self-Improvement",
    "2608.27311": "Verify Smarter, Evolve Further (HarnessLens)",
    "2607.13683": "Self-Evolving Agent Harnesses via Gated Semantic Quality-Diversity",
    "2607.13285": "Harness Handbook",
    "2606.09498": "Self-Harness: Harnesses That Improve Themselves",
}
# Still to verify (cite only with 'ID to be re-verified' note):
pending = ["2608.25593", "2608.20169", "2604.06753", "2605.29668", "2607.05752",
           "2607.11399", "2607.18235", "2605.26731"]
out = {"verified": verified, "pending": pending,
       "note": "verified via alphaxiv.org/arxiv.org 2026-09-03; pending IDs must be resolved before submission"}
Path(__file__).resolve().parent.parent.joinpath("artifacts/day2/arxiv_id_verification.json").write_text(
    json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
