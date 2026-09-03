"""P0 experiment chain (external-review priorities):

Stage 1: old proposer protocol x Qwen builder      (TTHE optimize, target=GLM)
Stage 2: old proposer protocol x DeepSeek builder  (TTHE optimize, target=GLM)
Stage 3: 36 disjoint-item evaluation of all old-protocol candidates (diversity selection set)
Stage 4: per-builder greedy top-6 selection (same rule as a6_selection.json)
Stage 5: eval151 matrix for the 12 selected harnesses (target=GLM)
Stage 6: SECOND TARGET: backup GLM solver_cache, switch config target to Qwen3.8-Flash,
         eval151 for {bare, react, A6, D8, hpc4} = 14 harnesses, then restore config+cache.

Everything logged to artifacts/day2/p0_chain.log. Keys: paratera ziyang for builder/qwen-target
stages; ziqian (GLM) restore is a cache restore so no re-run of GLM eval151 is needed.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TTHE = ROOT / "external" / "TTHE"
AGENTS = TTHE / "text_to_sql" / "agents"
ART = ROOT / "artifacts" / "day2"
LOG = open(ART / "p0_chain.log", "a", encoding="utf-8")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


def run(cmd, env, cwd=TTHE, timeout=7200):
    log("RUN: " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                       timeout=timeout, shell=False)
    (ART / "p0_chain_stdout.txt").open("a", encoding="utf-8").write(
        f"\n===== {' '.join(cmd)}\n{r.stdout[-3000:]}\nERR:{r.stderr[-1500:]}\n")
    if r.returncode != 0:
        log(f"  exit={r.returncode} (continuing chain)")
    return r


def ziyang_env():
    env = os.environ.copy()
    for line in (ROOT / "experiment" / ".env_tthe_ziyang").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
    return env


def collect(harnesses, out_name, tag):
    cmd = [sys.executable, "../../experiment/tthe_collector.py", "--split", "split_eval151.json",
           "--harnesses", ",".join(harnesses), "--workers", "6", "--out", out_name]
    run(cmd, ziyang_env())
    import pandas as pd
    return pd.read_parquet(ROOT / "artifacts" / "outcomes" / out_name)


def select_top6(df, cands, disjoint_tasks):
    import numpy as np
    sub = df[df.harness_id.isin(cands) & df.task_id.isin(disjoint_tasks)]
    piv = sub.pivot_table(index="task_id", columns="harness_id", values="harness_correct")
    piv = piv.dropna(axis=1)
    cands = list(piv.columns)
    bare = df[(df.harness_id == "bare") & df.task_id.isin(disjoint_tasks)].set_index("task_id")["harness_correct"]
    fixsets = {h: frozenset(piv.index[(piv[h] == 1) & (bare.reindex(piv.index) == 0)]) for h in cands}
    stats = {h: float(np.mean([np.mean(piv[h] != piv[h2]) for h2 in cands if h2 != h])) for h in cands}
    sel, pool = [], list(cands)
    for _ in range(min(6, len(cands))):
        best = max(pool, key=lambda h: (len(set().union(*[fixsets[x] for x in sel + [h]])), stats[h], h))
        sel.append(best)
        pool.remove(best)
    return sorted(sel)


def main():
    import pandas as pd
    split = json.loads((ROOT / "experiment" / "split_eval151.json").read_text())
    all_items = {f"{d}#{i}" for d, idxs in split["by_db"].items() for i in idxs}

    # --- stages 1-2: old protocol generation for qwen / dsexp builders (target stays GLM) ---
    for tag, model in (("oldqwen", "Qwen3.8-Flash"), ("oldds", "DeepSeek-V4-Flash-Vision-Exp")):
        existing = list(AGENTS.glob(f"cand_{tag}_*.py"))
        if len(existing) >= 10:
            log(f"stage gen {tag}: {len(existing)} candidates already exist, skip")
            continue
        log(f"stage gen {tag} via optimize --model {model}")
        run([sys.executable, "-m", "text_to_sql.optimize", "--db", "card_games",
             "--group", "2", "--max-rounds", "2", "--model", model, "--run-name", tag],
            ziyang_env(), timeout=10800)

    q_cands = sorted(p.stem for p in AGENTS.glob("cand_oldqwen_*.py"))
    d_cands = sorted(p.stem for p in AGENTS.glob("cand_oldds_*.py"))
    log(f"candidates: qwen={len(q_cands)} dsexp={len(d_cands)}")
    if len(q_cands) < 2 or len(d_cands) < 2:
        log("too few candidates generated; aborting chain for safety")
        return

    # --- stage 3: 36 disjoint-item selection set ---
    df1 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix.parquet")
    sel_items = sorted({t.split("#")[0]: [] for t in all_items}.keys())  # dbs in split
    # 36 disjoint = all card_games indices seen in day-1 matrix minus eval151 card_games items
    d1 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_bird_matrix.parquet")
    day1_cg = sorted({int(t.split("#")[1]) for t in d1.task_id if t.startswith("card_games")})
    eval_cg = set(split["by_db"]["card_games"])
    disjoint36 = [i for i in day1_cg if i not in eval_cg]
    log(f"disjoint selection items: {len(disjoint36)}")
    sel_split = {"by_db": {"card_games": disjoint36}}
    (ROOT / "experiment" / "split_sel36.json").write_text(json.dumps(sel_split))

    allc = ["bare"] + q_cands + d_cands
    df_sel_path = "tthe_sel36_matrix.parquet"
    df_sel = pd.read_parquet(ROOT / "artifacts" / "outcomes" / df_sel_path) \
        if (ROOT / "artifacts" / "outcomes" / df_sel_path).exists() else None
    if df_sel is None or df_sel.harness_id.nunique() < len(allc):
        # collector with custom split file name relative to experiment/
        cmd = [sys.executable, "../../experiment/tthe_collector.py", "--split", "split_sel36.json",
               "--harnesses", ",".join(allc), "--workers", "6",
               "--out", df_sel_path]
        run(cmd, ziyang_env(), timeout=14400)
        df_sel = pd.read_parquet(ROOT / "artifacts" / "outcomes" / df_sel_path)

    # --- stage 4: selection ---
    q6 = select_top6(df_sel, q_cands, set(f"card_games#{i}" for i in disjoint36))
    d6 = select_top6(df_sel, d_cands, set(f"card_games#{i}" for i in disjoint36))
    log(f"selected qwen-old: {q6}")
    log(f"selected dsexp-old: {d6}")
    (ART / "old_protocol_selection.json").write_text(json.dumps(
        {"qwen": q6, "dsexp": d6, "rule": "greedy union fixsets then disagreement on 36 disjoint items"}, indent=1))

    # --- stage 5: eval151 for the 12 selected (GLM target) ---
    df151r4 = ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix_round4.parquet"
    if not df151r4.exists():
        collect(q6 + d6, "tthe_eval151_matrix_round4.parquet", "old-protocol eval151")
    log("stage 5 done")

    # --- stage 6: second target (Qwen3.8-Flash) ---
    cfg = TTHE / "config.yaml"
    cfg_bak = ART / "config.yaml.glm.bak"
    shutil.copy(cfg, cfg_bak)
    cache = TTHE / "text_to_sql" / "logs" / "solver_cache.json"
    cache_glm_bak = ART / "solver_cache.glm.bak"
    if cache.exists() and not cache_glm_bak.exists():
        shutil.copy(cache, cache_glm_bak)
    # swap target model
    txt = cfg.read_text(encoding="utf-8")
    txt2 = txt.replace("solver_model: GLM-5.3-Flash", "solver_model: Qwen3.8-Flash")
    cfg.write_text(txt2, encoding="utf-8")
    log("config target switched to Qwen3.8-Flash; cache rotated")
    if cache.exists():
        cache.rename(ART / "solver_cache.qwen_round_p0.tmp")  # clear for qwen target
    try:
        second = ["bare", "react"] + \
                 json.loads((ROOT / "artifacts/day2/populations_eval151.json").read_text())["D6_dsexp_freeform"] + \
                 ["cand_bird_g1_b1r0_g1", "cand_bird_g1_b1r1_g0", "cand_bird_g1_b1r1_g1",
                  "cand_bird_g1_b2r0_g1", "cand_bird_pop1_b0r0_g0", "cand_bird_pop1_b0r0_g1"] + \
                 ["hpc_schema", "hpc_hint", "hpc_repair", "hpc_vote3"]
        collect(second, "tthe_eval151_qwentarget.parquet", "second-target eval151")
    finally:
        # restore GLM config + cache
        shutil.copy(cfg_bak, cfg)
        qcache = ART / "solver_cache.qwen_round_p0.tmp"
        if qcache.exists():
            qcache.rename(TTHE / "text_to_sql" / "logs" / "solver_cache.qwentarget.json")
        if cache_glm_bak.exists():
            shutil.copy(cache_glm_bak, cache)
        log("config + GLM cache restored")
    log("P0 CHAIN COMPLETE")


if __name__ == "__main__":
    main()
