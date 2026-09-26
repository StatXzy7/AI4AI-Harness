# Shared caption draft — kept outside LaTeX

Figure 1: Coverage, repeatability, and selection on 386 complete MATH tasks. Oracle coverage matches executions, not tokens/calls; headroom uses repeat means. Persistent task counts require at least one generated member to win/lose against baseline in all three repeats; the sole win is extraction-sensitive. Intervals are 95% bootstrap CIs. Program drawings are schematic.

## Shared alternative text

Eight generated programs plus a baseline are compared with nine identical baseline slots, using three repeats on 386 complete MATH-500 tasks. Oracle coverage rises with the number of executions and reaches 98.70% in both arms at 27 executions. Repeat-mean estimated headroom is 2.33 pp for generated programs and 2.16 pp for identical code. Residual score-pattern correlation is 0.789 versus 0.006, with confidence intervals. Persistent scored losses span 100 tasks; persistent wins occur on one extraction-sensitive task. Two discovery repeats freeze per-task choices and the best fixed comparator; the held-out repeat scores gain, rotating across three folds. Clone-adjusted held-out gain is −0.26 pp, with 95% interval [−1.45, +0.95] pp; specialization remains unresolved. A separate frozen feature selector chooses the baseline on all 386 tasks and gains 0.00 pp.

## Layout descriptions

- A places a shared illustrated control and explicit fold diagram above three result columns.
- B uses a shared illustration above three horizontal evidence rows, each pairing a main finding with its supporting result.
- C uses an illustrated board: setup at upper-left, coverage at upper-right, repeatability at lower-left, and useful selection at lower-right.
