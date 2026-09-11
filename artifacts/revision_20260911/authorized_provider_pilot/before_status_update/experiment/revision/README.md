# Offline replay and runtime recovery

This directory implements the post-review correction of the **original gate** experiment. It does not implement or claim completion of the new A–D experiments. Start with `review-stage/REVISION_20260910.md` for status and claim boundaries.

## 1. Result replay without model APIs

From the repository root (locally verified with Python 3.13.9):

```powershell
python -m experiment.revision.verify
python -m unittest experiment.revision.test_replay experiment.revision.test_sensitivity experiment.revision.test_fingerprint experiment.revision.test_selection -v
python -m experiment.revision.replay --n-boot 10000
python -m experiment.revision.sensitivity --n-boot 10000
python -m experiment.revision.cost_audit
python -m experiment.revision.fingerprint
python -m experiment.revision.selection
python -m experiment.revision.render
Push-Location paper/latex
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
Pop-Location
```

The first command checks the archived, inspected bundle. Regeneration can change
file hashes (including PDF metadata); `verify` intentionally reports STALE until
the regenerated results and PDF have been inspected and `verification.json` has
been refreshed. It is an integrity check of a reviewed snapshot, not an automated
certificate of scientific validity or visual quality for a new build.

Observed replay dependencies: `numpy==2.3.5`, `matplotlib==3.10.9` (recorded in the runtime manifest). LaTeX was compiled with TeX Live 2026 and the repository's ICLR 2027 style. No API client or external TTHE import is needed for this level. A new venv with no system site packages reproduced the full 10,000-bootstrap primary/core and K-matched/R2 result objects exactly, and all 18 tests passed there. See `artifacts/revision_20260910/clean_environment_replay.json` and `requirements-replay.lock.txt`. This verifies offline replay in the same checkout, not a new machine or restoration of the full API runtime.

Inputs are the exact files in the historical `primary_input_manifest.json` and `bc_input_manifest.json`, with their frozen length and SHA-prefix checks. New analysis outputs record full SHA256 hashes. The baseline for all revised arms comes from AD; tasks come from the explicit split, never from successful-row intersection. All 18 cells and all callable admitted candidates remain, including a bare-only pool when K=0.

The canonical row index records target, harness/source hash, task, repeat, cache condition, both judges, collection group, and source file/line. Arm membership is versioned through generation JSONs and their hashes. Future repeats must have unique run identity in addition to repeat/cache; the historical data do not offer all prospective trace fields. Per-record code hashes are 16-digit prefixes of normalized-text SHA256, not original-byte full hashes.

`corrected_analysis.json` contains full-precision results and the analysis design. `sensitivity.json` separately records exact K matching with bare retained and R2 cache-off comparisons without bare (no matched bare rerun exists). R2 retains all 18 cells including singleton pools; the old 16-cell subset is diagnostic only. `cost_audit.json` reports logical calls including cached calls, not billable requests: none of the 153,600 canonical candidate rows contains token usage, so dollar/token costs cannot be recovered from these traces alone. `paper_assets_manifest.json` binds that JSON to generated TeX and figure files by SHA256. The large canonical row index and smoke outputs are derived files and can be regenerated; the compact result JSON, runtime snapshot and manifests are the reviewable evidence package. Original analysis artifacts remain unchanged.

The exact sign-flip reference test assumes cell-contrast sign symmetry and conditions on current tasks. The CI resamples shared database/task indices and generation seeds within fixed builders. Do not present the p-value as causal randomization inference or infer new-target/execution variance from the archived records.

## 2. Instrument checks without model APIs

The twenty-five replay/sensitivity/fingerprint/selection/verification tests cover K=0/K=1, nonmonotone headroom, decomposition, paired identical-arm nulls, within-database sampling, fixed-builder sampling, exact sign flips/Holm, shared bare, missing members, conflicting duplicates, repeat/cache separation, source-row provenance and manifest tampering.

Additional integration tests exercise asymmetric candidate counts, K=0, singleton R2 populations, separate repeat collection identity, exact subset enumeration, cost denominators, and rejection of conflicting shared-code provenance.

These are not full gate-v2 calibration. The historical gate/stub suite remains archived. Development probes for all eight strategy contracts and a partial real-interface adapter now exist (see section 5 and `review-stage/GATE_V2_CONTRACTS.md`). Independent calibration, semantic adjudication and the common raw-pool experiment remain required before B is passed.

## 3. Runtime snapshot and full API rerun

`artifacts/revision_20260910/runtime_snapshot.zip` contains a patch against upstream TTHE commit `69a614d04f2a7f3eacb64a63193078ab4be56ba5`, 385 measured harness/bare sources and six positive/negative controls. The manifest lists full byte hashes for every member, dependency versions, and five modified tracked runtime files. All 385 measured normalized source hashes matched the recorded hash prefixes. The patch was checked against an isolated git index of the upstream commit; this does not prove a clean execution environment has been reproduced.

To restore in a new location: obtain [TTHE upstream](https://github.com/junnie00/TTHE), check out that exact commit, extract the snapshot to a temporary directory, verify all member SHA256 values against `snapshot_manifest.json`, apply `runtime.patch` using `git apply --check` then `git apply`, and copy only the archived `text_to_sql/agents/*.py` into the matching agents directory. Use the pinned upstream dependency instructions plus the local modification manifest; confirm raw-data paths, official scorer, gates and environment dependencies before running a collector. Do not overwrite an existing researcher checkout to test restoration.

API rerunning additionally requires the frozen provider/model settings, authorized credentials and a concrete budget. Use environment-variable credentials; no credential is supplied by this package. Caller count is not determined by population K: record per-request input/output tokens and count. The new A–D plan is not frozen or runnable yet. The snapshot is an internal recovery artifact, not a completed anonymous submission package or a credential-revocation certificate.


## 4. Canonical exploratory W1/W3 results

`fingerprint.json` retains W3's legacy lossy SQL transform to isolate loading differences. It is not semantic normalization; all correlations are descriptive over dependent pairs. R2 SQL rates require two nonempty SQL strings (27,936 pairs); calls/verdict rates retain all 28,000 records.

`selection.json` uses a newly recorded deterministic schedule retaining the old seed, 100 database splits, 200 random draws and seven candidate-selection rules, k=4/8. Old set-derived cell order was not archived, so this does not recover exact historical random draws. Candidate-only and common-bare-inclusive results are separate. Dev-fixed chooses one member using development data with canonical member-name ties; it is distinct from held-out best-fixed. The overlapping splits are not independent experiments. Old cell-only CIs are withdrawn; inference including database/task resampling and re-selection remains outstanding. No independent utility or routing gain is established.

The isolated-venv W1/W3 rerun reproduced both JSON files byte for byte (`clean_environment_exploratory.json`). Current inspected manuscript snapshot passes 42 source/result/asset hashes and 25 tests; see `verification.json` for the exact binding.

## 5. Gate-v2 development instrument (not released)

See `review-stage/GATE_V2_CONTRACTS.md`. Run `python -m unittest experiment.revision.test_gate_v2 -v` for synthetic controls. The separate `test_gate_runtime_adapter` suite and `gate_development_report` require the local restored TTHE control sources. The latter produces a labeled development report and a separate 14-case semantic-review packet without expected labels/current verdicts. No independent calibration or semantic adjudication is complete.

Four families always require semantic review after structural probes: hint/format prompts, two-view formulations, and error-class-specific action meaning. A structural `pass` does not grant production admission. Ten discovered adversarial implementations no longer receive automatic passes. Development counts and pending cases are reported separately; review-required is not treated as a correct rejection.

The combined revision suite now contains 36 tests (25 statistical/exploratory, 9 synthetic gate, 2 runtime adapter); the existing paper snapshot remains bound to its 25 statistical/exploratory tests. `gate_v2_development_verification.json` binds the separate development checks and source hashes.

## 6. Repeat/clone planning simulation

`python -m experiment.revision.repeat_planning --n-sim 1000` generates24settings×1000simulateddatasets. `python -m experiment.revision.render_planning` renders the planning figure. Tests: `python -m unittest experiment.revision.test_repeat_planning -v`. See `review-stage/REPEAT_PLANNING.md` for estimands and assumptions. The 2.5–97.5% bars are simulated-dataset quantiles, not experiment CIs or power/coverage results. No sample-size or cost-matching approval is conferred.

The same-checkout isolated-venv rerun reproduced the simulation JSON byte for byte. There are now41 combined revision tests; the paper snapshot and gate-development snapshots retain their own scoped test counts. Simulation/source/figure/report bindings are in `repeat_planning_verification.json`.

## 7. Candidate database/repeat inference calibration

`python -m experiment.revision.repeat_inference --n-sim 300 --n-reference 3000 --n-boot 399` and `python -m experiment.revision.render_inference` produce the development calibration and plot. See `review-stage/REPEAT_INFERENCE_CALIBRATION.md` for the fixed-anchor fresh-policy expectation target and its distinction from stable headroom or a fitted policy's conditional value.

The candidate percentile bootstrap is **not ready**: conservative intervals in the six non-cache settings and systematic false positives under cache coupling. Database/task draws and within-half repeat draws preserve pairing; no stored repeat record crosses a directional split, but the cache stress deliberately shares underlying results. Do not use this candidate as formal analysis merely because implementation tests pass.

The completed run used the existing isolated replay environment; no second full Monte Carlo rerun is claimed. Five new tests bring the combined revision suite to46, all passed. Existing English manuscript snapshot remains scoped to its preceding25 tests. Source/result/report/plot hashes are bound in `repeat_inference_verification.json`; the paper PDF was not changed.

## 8. Stable-complementarity identification checks

Run `python -m experiment.revision.stable_witness` and `python -m unittest experiment.revision.test_stable_witness -v`. Exact constructed examples demonstrate why a positive fresh gain over a discovery-selected fixed comparator does not identify stable headroom, and why subtracting two witnesses/lower bounds does not bound a stable-headroom contrast.

`validation_differences` retains every fixed comparator. `stable_bounds` propagates supplied simultaneous probability bands; `contrast_bounds` uses lower-real minus upper-clone and the reverse endpoint. `hoeffding_bands` is a transparent conservative benchmark under stationary independent validation blocks, allowing dependence within each block. It neither verifies those assumptions nor supplies useful precision automatically. See `review-stage/STABLE_IDENTIFICATION.md`; do not substitute these fixed-pool checks for full A–D evidence.

Six new behavioral tests bring the passing revision suite to52. Source/report/result bindings are in `stable_identification_verification.json`. The bilingual manuscript comparator wording was updated and recompiled; empirical results remain unchanged. The English snapshot still has25 relevant statistical/exploratory tests, included in this52-test run.

## 9. Full local collection stack with a loopback provider

Use the separate Windows environment `artifacts/revision_20260910/runtime_env/Scripts/python.exe`, with dependencies in `artifacts/revision_20260910/requirements-runtime.lock.txt`. Run `python -m experiment.revision.runtime_probe` and `python -m unittest experiment.revision.test_runtime_probe -v`. The original collector, SDK, bridge, cache, SQLite layer and project scorer execute on temporary synthetic BIRD-format data. No production credentials or BIRD examples are loaded; the provider endpoint is loopback only.

Six integration checks reproduce current cache, resume-identity, request-count, usage-retention and transmitted-temperature defects. Passing these tests confirms the diagnosis, not a repaired production runtime. The complete58-test revision suite passes in this separate environment. The older replay environment lacks the SDK/YAML dependencies needed by the new integration tests; use the runtime environment for whole-suite discovery. See `review-stage/RUNTIME_RESTORATION.md` and `runtime_probe_verification.json`. Empirical results and manuscript assets are unchanged.

## 10. Versioned fresh acquisition and request ledger

`python -m experiment.revision.fresh_collect --config reviewed_acquisition.json` runs the new collector; `python -m unittest experiment.revision.test_fresh_runtime -v` exercises it entirely through loopback fixtures. Use the runtime environment. See `review-stage/FRESH_ACQUISITION.md` for the required configuration, changed execution policies and explicit remaining limitations.

The SQLite ledger binds the full declared run identity and records logical calls, samples, transport attempts, responses and usage. Unknown requests block completion; invalid input/background-thread states persist across resume. Historical upstream code is unchanged. Race harnesses with unjoined work currently stop the run and require task-process isolation before the original full population can be evaluated. Do not silently omit them.

Eight new tests bring the passing complete revision suite to66. A retained4-cell bare/clone fixture made4 HTTP requests; a new process resumed with0 additional requests. Artificial token counts are not real costs. Source/result/test bindings are in `fresh_runtime_verification.json`; no empirical BIRD outcomes or paid provider calls were added.

## 11. Per-task Windows process isolation for race harnesses

`python -m experiment.revision.isolated_collect --config reviewed_acquisition.json` adds an explicit `worker_wall_seconds` and `drain_seconds` to the fresh configuration. The worker is created suspended, assigned to a Job Object, then started. SQL is frozen before bounded draining of same-task requests; the parent verifies an empty local job before importing the worker ledger. Race harnesses are supported when their requests settle; unresolved workers preserve the returned answer and pending evidence and stop the acquisition.

Run `python -m unittest experiment.revision.test_isolated_collect -v` in the Windows runtime environment. Five new tests cover real race repeats, expiry/timeout, process-tree termination and actual SQLite hot-journal recovery. The full revision suite has71 passing tests. See `review-stage/TASK_PROCESS_ISOLATION.md`, `isolation_smoke.json`, `isolation_tests.txt` and `isolation_verification.json`.

Local process termination does not establish provider completion, statistical independence or final cost. Do not silently discard pending cells, score them as wrong or resample them; the scientific failure policy and A–D evidence are still incomplete. Historical runtimes and manuscript assets are unchanged.


## 12. 真实提供方先导审阅包（未运行）

阶段12历史包见 `review-stage/PROVIDER_PILOT.md`；当前v2执行修订见 `review-stage/PROVIDER_LAUNCH_GUARDS.md` 与 `artifacts/revision_20260910/launch_guards/`。两道已曝光开发题、12cell范围不变。一次原提供方模型列表只读核验返回200；真实生成请求为0。16–24 HTTP只是所选源码/零重试配置的静态范围，98,304是输出额度而非总tokens或金额保证。v2拒绝DRAFT启动；usage未知时保留答案与父pending、停止下一cell及自动续跑。仍待账户费用界、预算授权及最终冻结，这些检查不能替代金额上限。


## 14. W1 joint positive-weight re-selection sensitivity

Run `python -m experiment.revision.selection_weights --draws 199 --out NEW_OUTPUT.json` and `python -m unittest experiment.revision.test_selection experiment.revision.test_selection_weights -v`. Choose a new output path; existing results are not overwritten. The 100 original overlapping splits, all methods, both k values, both bare views and all18 cells share each positive task-weight draw. Original random subsets are replayed and bound. A uniform audit row must match canonical choices and scores.

The retained `selection_weights.json` / `.npz` contain199 perturbations, a uniform row, 28 summaries and input bindings. These are sensitivity quantiles, NOT confidence intervals; generation seeds and observed executions remain fixed, and only about5 draws populate each2.5% tail. See `review-stage/W1_WEIGHT_SENSITIVITY.md` for exact empty-side bootstrap probability, the repaired floating-point tie regression, checks and remaining W1 inference requirements. The ten selection tests and original42 paper checks pass; manuscript data and PDFs are unchanged.

## 17. Gate development semantic adjudication

`review-stage/GATE_SEMANTIC_ADJUDICATION.md` and `artifacts/revision_20260910/gate_semantic_adjudication/` record14 exposed development cases reviewed by gpt-5.5, separately from the GPT-6 implementer. The rule and packet were fixed before adjudication. Four cases conform and ten do not; all40 evidence references are checked against the original traces. Eight structural review-required cases become four development semantic conforms and four nonconforms; six structural failures remain failures. No result becomes production admission. These are development adjudication counts, not held-out calibration error rates; the original gate contract/report remain unchanged historical artifacts, and B release remains not ready.

## 18. First independently authored control check (failed)

`independent_gate_controls.py` contains32 frozen controls authored from the public contract by a new-context gpt-5.5. `independent_gate_measure.py` recorded one full evaluation; do not rerun it against the existing output directory. `--package-only` can recreate missing evidence packaging from existing results without evaluating controls; COMPLETE hashes identify the complete package. Run `python -m unittest experiment.revision.test_independent_gate_measure -v` for mock fault tests, not the independent control measurement.

See `review-stage/GATE_INDEPENDENT_CALIBRATION.md` and `artifacts/revision_20260910/gate_independent_controls/`. A third model reviewed source and traces without author labels or automatic verdicts. Three reference labels are disputed; among29 undisputed controls, three of13 conforming controls were rejected and all16 nonconforming controls were rejected. The finite check failed. Original source, labels, measurement, initial/final adjudication and72 exact evidence references remain available. Instrument fixes need a new version and new controls; these32 are now exposed. B remains incomplete. The bilingual appendix now reports these diagnostic results without replacing historical benchmark outcomes.

## 19. Gate-v3 已曝光回归

`gate_v3.py`是独立版本，旧v2保留冻结哈希。`test_gate_v3.py`测试10项；与旧gate/adapter/measurement共23项相关测试通过。`python -m experiment.revision.gate_v3_report`使用原salt生成32例完整回归；已有输出拒绝覆盖。结果6 pass、13 fail、13 review_required，不复用旧裁决生成准入；未来分解歧义例还需要额外独立裁决。详见`review-stage/GATE_V3_REGRESSION.md`及`artifacts/revision_20260910/gate_v3_repair/verification.json`。未改生产默认版本或论文首测表，新独立校准仍待完成。

## 20. Gate-v3 新独立控制检验

`independent_gate_v3_measure.py`保留旧runner版本，固定五语义组并隐藏仪器派生元数据；2项新mock测试通过。`gate_v3_independent/`保存32例首次完整测量、无标签packet、32源码/20语义裁决及101条证据核验。合并后31无争议参考为14接受/16拒绝/1未决，另1参考争议；有限检验not ready。详情见`review-stage/GATE_V3_INDEPENDENT.md`；英文18页、中文20页已同步。不得重跑或覆盖已曝光首测以声称独立校准通过。

## 21. Classification response profiles

`classification_profiles.py` uses source-assigned finite response sequences for four exposed controls. `classification_profile_report.py` collected84 traces (28 primary,56 diagnostic), with no automatic admission. `python -m unittest experiment.revision.test_classification_profiles -v` runs11 synthetic/mock tests. See `review-stage/CLASSIFICATION_RESPONSE_PROFILES.md` and `classification_profiles/verification.json` under the revision artifacts.

The historical measurement runner is preserved as `classification_profiles/measurement_report_source.py` data. The current runner subsequently gained persistent input-change invalidation; lineage records that distinction. Do not call its collect or package-only command on the already completed historical output. The role map was independently fixed before measurement; alternate response profiles cannot replace the assigned primary. Correct-category injection tests consumption and downstream actions, not classifier accuracy. Production integration and independent calibration remain incomplete.

## 22. Legacy generation extraction audit

`python -m experiment.revision.generation_extraction_audit` audits the fixed36 C/D generation logs and writes `generation_extraction/audit.v2.json`; identical deterministic output is permitted, a different existing result is rejected. It isolates the archived pure extractor through AST and never imports the generation client or executes candidates. `python -m unittest experiment.revision.test_generation_extraction_audit -v` runs3 finite syntax regressions.

All108 format_guard attempts failed neutral validity. Three valid synthetic Python forms are cut at inner SQL fences without the legacy truncation flag. Full historical builder messages are not available through these logs/extracted files; three raw/log conflicts remain unassigned, and runtime source identity is not inferred from the review commit. See `review-stage/GENERATION_EXTRACTION_AUDIT.md`. A new common-pool generator must preserve full replies and repair extraction; this audit does not change or relabel old results.

## 23. Fixed-attempt common-pool acquisition

`common_pool.py --config CONFIG --prepare-only` prepares bindings without keys or network; DRAFT plans refuse execution. A reviewed FROZEN plan plus separately authorized costs is required for provider use. The producer makes exactly three planned attempts per slot unless transport/response/usage uncertainty stops the pool, commits content-encoding-raw body bytes before decoding/extraction, and never imports or admits candidates. Completed ledgers can be exported without new calls; pending tasks cannot automatically resume.

Run `python -m unittest experiment.revision.test_common_pool -v` for13 offline tests. `python -m experiment.revision.common_pool_demo --output NEW_DIRECTORY` uses only a loopback HTTP server with artificial responses/tokens; existing output is rejected. Retained six-request/zero-repeat evidence is in `artifacts/revision_20260910/common_pool_generation/loopback/`. See `review-stage/COMMON_POOL_GENERATION.md`; software readiness does not clear scientific B or real provider launch.

## 24. Archived-candidate runtime interface diagnostic

`runtime_gate_diagnostic.py` runs frozen gate-v3 through the existing SQLHarness adapter for the seven source-selected archived C candidates. The stage22 manifest retains format_guard as unavailable. The retained first measurement is `artifacts/revision_20260910/runtime_gate_bridge/stage24/`; do not rerun it. It contains27 synthetic scenarios plus one derived cross-class record. COMPLETE binds both manifest and results; no candidate is admitted. See `review-stage/RUNTIME_GATE_DIAGNOSTIC.md` for response-format/attribution limitations and the observed two-view execution shortfall. Benchmark outcomes and provider clients are not used.

## 25. Source-assigned response profiles and SQLite feedback

`runtime_response_profiles.py` supplies schema JSON, resolves a source-declared dedicated subquestion field, and executes fixed SQL against a fresh in-memory SQLite database. `runtime_response_report.py` retained11 development scenarios in `artifacts/revision_20260910/runtime_response_profiles/`; do not rerun the completed measurement. `python -m unittest experiment.revision.test_runtime_response_profiles -v` runs4 offline behavioral tests. No profile automatically admits a candidate. Source/trace review and the bilingual Appendix G paragraph distinguish full-schema context from dropping linked restrictions. See `review-stage/RUNTIME_RESPONSE_PROFILES.md`. Independent calibration and the common-pool policy experiment remain incomplete.

## 26. Unified Gate-v4 development measurement

`gate_v4.evaluate` preserves five v3 strategy probes and routes three strategies through explicitly assigned response profiles. Unknown profiles remain unresolved without execution; typed traces require independent review. `python -m unittest experiment.revision.test_gate_v4 experiment.revision.test_runtime_response_profiles -v` runs8 offline tests. The fixed39-scenario exposed regression is retained in `artifacts/revision_20260910/gate_v4_regression/`; do not rerun or overwrite it. Its instrument freeze is only for independent reference checks, not provider or scientific launch. See `review-stage/GATE_V4_CONTRACT.md` and `GATE_V4_REGRESSION.md`.

## 27. Gate-v4独立参考首测前验收

`independent_gate_v4_measure.py`准备排他目录单次测量、完整依赖一致性与无标签真实轨迹包；3专项测试通过。`gate_v4_calibration/`保存新32参考的初始快照、gpt-5.5盲源码审核与vote合同补充裁决。合并为12符合/16不符合/4未决，6/10 not ready，尚未执行measure。schema接口和vote采样参考正修正，必须重新静态审核后才可冻结运行；旧仪器、论文与历史结果不改。报告见`review-stage/GATE_V4_REFERENCE_PREFLIGHT.md`。

## 28. Gate-v4统一参考首测与双语论文记录

`gate_v4_reference_check/measurement/`保留一次32参考/124场景、固定35输入依赖、COMPLETE与盲包。结构4pass/6fail/22review；首次盲审混合17接受/15拒绝，gv4r032误放，预定有限验收not ready。`trace_review_clarification.json`及`clarified_hybrid_result.json`独立保存两项定向澄清，16/16全一致不覆盖首次结果、不作新独立通过。132条源码/轨迹/澄清引用核验，中英文附录同步并通过构建和视觉检查；报告见GATE_V4_REFERENCE_CHECK.md。旧来源与PDF/日志均有先行快照。


## Stage 29：固定运行环境实际恢复

固定上游与冻结 ZIP 已在独立目录恢复，新建 venv 锁定29依赖，444 Python文件编译通过。首次 git apply 在父仓库内静默跳过的问题已定位并通过独立 Git 边界解决；失败证据保留。离线 mock/demo 通路通过，仅支持源码与基础运行恢复，不提供真实模型或科学结论复现证据。详见 `review-stage/RUNTIME_RESTORATION_CHECK.md` 与 `artifacts/revision_20260910/runtime_restore_check/`。A–D/W1未完成，论文与历史结果本轮不变。


## Stage 30：W1拟议百分位区间的精确反例

固定九库二元状态构造、canonical重选择及并列规则，精确期望与60项实现对照通过。p=0.1/0.9时，拟议正权重百分位区间的覆盖率上界为61.257951%，严格不足95%；这不是BIRD覆盖率。已排除该区间的普遍覆盖保证，中英文W1附录同步，实测表和主文不变。见 `review-stage/W1_EXACT_COUNTEREXAMPLE.md`、`artifacts/revision_20260910/w1_exact_counterexample/`。W1总体推断仍未完成；后续方法必须先固定总体与随机层级，不能直接把原扰动分位数写成CI。A–D真实实验和账户费用条件仍未解决。
