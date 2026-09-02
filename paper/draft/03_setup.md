# §3 Experimental Setup

*(draft v1, 2026-09-02; evidence: PROBLEM_FREEZE.md v7, EXPERIMENT_PLAN.md, split_eval151.json)*

## 3.1 Harnesses and harness value

Following the harness-abstraction of TTHE, a **harness** $H$ is a program that wraps a
frozen target model $M$: it receives the natural-language task input $x$, issues one or
more calls to $M$, optionally executes intermediate artifacts (e.g., SQL against the
database), and returns a final answer. Execution accuracy is scored programmatically.
For a task $x$, we define the **harness marginal value**

$$\Delta(x, H, M) \;=\; Y(x, H, M) - Y(x, H_0, M) \in \{-1, 0, +1\},$$

where $H_0$ is the bare single-call baseline and $Y \in \{0,1\}$ is programmatic
correctness; $+1$ is a *repair* (raw wrong, harness correct), $-1$ is
*harness-induced harm*. The deployment question that motivates this paper — predict
$\Delta$ before executing $H$ — presupposes that $\Delta$ is not almost-always zero.
A population of harnesses in which every harness reproduces the raw model's outcomes
offers nothing to predict or route over. Our first contribution is to take this
presupposition seriously and measure it.

## 3.2 Domain, target, and data splits

We instantiate the problem on **BIRD text-to-SQL** (SQLite), whose answers are judged
by execution against gold query results — no model-based grading. The target model is
frozen throughout: **GLM-5.3-Flash** served through an OpenAI-compatible endpoint
(temperature 0). All harnesses in a population call the same frozen target; builders
differ only in how harness *code* is produced.

We use two databases, `card_games` and `formula_1`. The **builder-visible set**
$D_{\mathrm{build}}$ contains 8 `card_games` questions. The **evaluation set**
$D_{\mathrm{eval}}$ contains **151 questions** (121 `card_games`, 30 `formula_1`),
with $D_{\mathrm{build}} \cap D_{\mathrm{eval}} = \emptyset$ enforced by construction.
Harness populations are
generated, frozen, and hashed *before* any evaluation on $D_{\mathrm{eval}}$; no
harness is re-tuned after evaluation.

## 3.3 Populations under comparison

Each AI-generated population contains $K=6$ harnesses produced under a fixed budget
and acceptance protocol. We compare:

- **Seed baselines**: `bare` (single call) and `react` (execution feedback loop,
  shipped with TTHE).
- **Condition A — proposer protocol (old)**: six candidates from TTHE's own optimize
  loop (GLM-5.3-Flash as builder), which sees 3 questions per round and edits harness
  code in a single turn. We select the 6 most behaviorally diverse of 12 candidates
  using *only* the 36 earlier-run questions disjoint from $D_{\mathrm{eval}}$
  (selection rule frozen before the 151-item evaluation).
- **Condition B — gated free-form, weak builder**: GLM-5.3-Flash writes full harness
  source under our generation gate (§6). **0/6 candidates were produced**: the model
  cannot reliably emit long code files. We report this as a generation-reliability
  finding, not a population.
- **Condition C — gated free-form, mid builder**: Qwen3.8-Flash, 6/6 generated.
- **Condition D — gated free-form, strong builder**: DeepSeek-V4-Flash (vision-exp
  checkpoint), 6/6 generated.
- **IR arm — compiled, no free-form code**: six harnesses compiled deterministically
  from declarative mechanism specifications by our Harness IR (§6.2); mechanism
  diversity is guaranteed by construction, isolating "what mechanisms do" from
  "can a builder write code".
- **Human positive control**: four hand-written harnesses with forcibly distinct
  execution paths (execute-and-repair, 3-vote, schema-linking, hint-first).

Every harness is accepted only after passing a smoke check (it runs and emits
executable SQL); the free-form arm additionally passes the execution-path gate of §6.

## 3.4 Pre-registered decision criteria

Before running any 151-item evaluation we froze, in the project decision log, the
following admission thresholds for treating a population as *behaviorally diverse
enough to route over*: union repair rate over bare errors $\geq 15\%$, oracle headroom
(vs. best fixed harness) $\geq 5$ pp, and $\geq 3$ harnesses with non-empty,
pairwise-distinct repair sets. Populations failing these thresholds are not subjected
to downstream value-prediction experiments. All results in §6 follow these rules;
nothing was re-defined after seeing the data.

<!-- NOTE(写作纪律): 所有 §6 数字到位后回填;本节引用的切分数与选择规则已与
     experiment/split_eval151.json、artifacts/day2/a6_selection.json 核对一致。 -->
