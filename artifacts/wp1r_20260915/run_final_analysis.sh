#!/bin/bash
# Final WP-1R/WP-2R analysis pipeline: run after all three arms are complete.
# Idempotent; safe to re-run.
set -e
cd /e/projects/AI4AI-Harness

echo "=== 1. Reconcile any residual unknown cells (parent must be dead) ==="
python -m experiment.revision.reconcile_cell --arm dev_real_cont2 || true
python -m experiment.revision.reconcile_cell --arm dev_real_cont || true

echo "=== 1b. Recover answers preserved on usage-unknown cells ==="
python -m experiment.revision.restore_usage_unknown dev_real_cont2 || true
python -m experiment.revision.restore_usage_unknown dev_real_cont || true
python -m experiment.revision.restore_usage_unknown eval_real_cont2 || true
python -m experiment.revision.restore_usage_unknown eval_real_cont || true
python -m experiment.revision.restore_usage_unknown eval_clone_cont || true

echo "=== 2. Seal merged arms ==="
python -m experiment.revision.wp1r_seal --merged \
  --arms eval_real,eval_clone,dev_real

echo "=== 3. WP-1R analysis (E1/E2/A8.6/E4) ==="
python -m experiment.revision.wp1r_analysis

echo "=== 4. WP-2R selector (E3/E_b) ==="
python -m experiment.revision.wp2r_selector

echo "=== 5. Render LaTeX macros + policy table ==="
python -m experiment.revision.wp1r_render

echo "=== 6. Unit tests ==="
python -m unittest experiment.revision.test_wp1r_merge 2>&1 | tail -3

echo "=== 7. Build PDF ==="
cd paper/latex
pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null
bibtex main > /dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex 2>&1 | tail -1
grep -ci undefined main.log || true
cd /e/projects/AI4AI-Harness
echo "=== DONE ==="
