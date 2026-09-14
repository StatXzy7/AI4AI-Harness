# Theory and minimal tests

The numeric examples below are constructed counterexamples, not measurements.

## Counterexample A: heterogeneous gaps without routing value

For two task strata, let `h0=(0.90, 0.60)` and `h1=(0.80, 0.20)`. The relative gap changes with the task, but `h0` is best in both strata. Thus `best-fixed = oracle = 0.75` and the ideal pre-execution single-action gain is `C_Z=0`. A nonzero interaction magnitude or disagreement does not imply a crossover in the preferred action.

## Counterexample B: residual coverage without single-action routing gain

Let each execution be independent with `p(h0)=0.8` and `p(h1)=0.7`. Then `P(h1 correct, h0 wrong)=0.14`, `P(h0 correct, h1 wrong)=0.24`, and the ex-post oracle after running both is `0.94`. Selecting one action before execution still chooses `h0` and obtains `0.8`; `C_Z=0`. Running both has a different (higher) call, token, latency and monetary cost budget.

## Conditional selection value

Let `Z` contain only deployment-time features available before any candidate answer is produced. Define `q_h(z)=E[Y_h|Z=z]` and `d(z)=q_1(z)-q_0(z)`. Under a common resource/cost scale and two actions,

`C_Z = E_Z[max(q0(Z),q1(Z))] - max(E_Z[q0(Z)],E_Z[q1(Z)])`

`= ( E_Z[|d(Z)|] - |E_Z[d(Z)]| ) / 2`.

The second form follows pointwise from `max(a,b)=(a+b+|a-b|)/2`, then subtracting the larger marginal mean. It is nonnegative and is positive only when the conditional relative advantage has both signs with positive probability. With costs, replace `q` by conditional net utility and separately charge for observing `Z` and the selector. For a pool `P` containing the fixed baseline,

`F_Z(P)=E_Z[max_{h in P} q_h(Z)]`, and

`Delta_Z(h|P)=E_Z[(q_h(Z)-max_{g in P}q_g(Z))_+]`.

This is different from one-run residual coverage `P(h correct and every g in P is wrong)`.

## Automated checks and scope

`python experiment/revision/insight_theory_tests.py` checks 625 grid cases with maximum absolute identity error `2.8e-17`, emits both counterexamples, and inventories the frozen input manifests. Output: `artifacts/revision_20260915/insight_analysis/insight_analysis.json` and `input_inventory.csv`. These are algebraic/coverage checks, not an estimate of population utility.

## Literature boundary

Rice's *The Algorithm Selection Problem* (1976) frames selecting algorithms from instance features. Gail and Simon (1985) define qualitative/crossover interaction as a change in which treatment is superior across subsets. Caruana et al. (2004) use validation-set forward selection from a model library for an ensemble objective. Wang et al. (2022) self-consistency samples multiple reasoning paths and aggregates them. These precede this project; the present addition is only the explicit measurement boundary and its audit on this archive.
