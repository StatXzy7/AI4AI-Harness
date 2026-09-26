# Caption draft — kept outside LaTeX

Figure 1: Coverage, repeatability, and selection on 386 complete MATH tasks. Oracle coverage matches executions, not tokens/calls; headroom uses repeat means. Persistent task counts require at least one generated member to win/lose against baseline in all three repeats; the sole win is extraction-sensitive. Intervals are 95% bootstrap CIs. Program drawings are schematic.

## Alternative text

An illustrated experiment compares eight generated programs plus a baseline against nine identical baseline slots, with three repeats per slot on 386 complete MATH-500 tasks. Three-fold validation freezes the task-wise choice and best fixed member using two repeats and evaluates gain on the third. The coverage plot shows all nine execution budgets and both arms reaching 98.70% oracle coverage at 27 executions. Repeat-mean estimated headroom is 2.33 versus 2.16 pp. Residual score-pattern correlation is 0.789 for generated members versus 0.006 for identical-code controls, with 95% intervals. Persistent scored losses span 100 tasks; persistent wins occur on one extraction-sensitive task. Clone-adjusted held-out gain is −0.26 pp with interval [−1.45, +0.95] pp, leaving specialization unresolved. A separate frozen feature selector chooses baseline on all 386 tasks and gains 0.00 pp.

## Interpretation notes

The interval for held-out gain is not an interval for population stable headroom. Subtracting the two headroom bars does not produce the held-out statistic. Same-task repeat transfer and pre-execution feature selection are separate evaluations. The full-budget tie is an observed oracle result, not a token/call-matched deployment or equivalence result. The 100 persistent-loss tasks mean at least one member shows that scored difference on all repeats, not that every program fails on every one of those tasks.
