"""Stage-6 resume: finish the second-target (Qwen3.8-Flash) eval151 collection.

The first attempt timed out at 7200s with all completed responses stored in
solver_cache.qwentarget.json. This script swaps config+cache back to the Qwen target,
re-runs the collector (cache hits replay finished work; only missing calls hit the API),
then restores GLM config + cache and archives the qwen cache.
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
ART = ROOT / "artifacts" / "day2"
LOG = open(ART / "p0_chain.log", "a", encoding="utf-8")


def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


def ziyang_env():
    env = os.environ.copy()
    for line in (ROOT / "experiment" / ".env_tthe_ziyang").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
    return env


cfg = TTHE / "config.yaml"
cache = TTHE / "text_to_sql" / "logs" / "solver_cache.json"
qcache = TTHE / "text_to_sql" / "logs" / "solver_cache.qwentarget.json"

cfg_bak = ART / "config.yaml.glm.bak"
assert cfg_bak.exists(), "GLM config backup missing"
cache_glm_bak = ART / "solver_cache.glm.bak"
assert cache_glm_bak.exists(), "GLM cache backup missing"

cfg.write_text(cfg_bak.read_text(encoding="utf-8").replace(
    "solver_model: GLM-5.3-Flash", "solver_model: Qwen3.8-Flash"), encoding="utf-8")
if cache.exists():
    cache.rename(cache.with_suffix(".tmp_glm_restore"))
shutil.copy(qcache, cache)
log("swapped to Qwen3.8-Flash target + qwen cache")

second = ["bare", "react"] + \
         json.loads((ROOT / "artifacts/day2/populations_eval151.json").read_text())["D6_dsexp_freeform"] + \
         ["cand_bird_g1_b1r0_g1", "cand_bird_g1_b1r1_g0", "cand_bird_g1_b1r1_g1",
          "cand_bird_g1_b2r0_g1", "cand_bird_pop1_b0r0_g0", "cand_bird_pop1_b0r0_g1"] + \
         ["hpc_schema", "hpc_hint", "hpc_repair", "hpc_vote3"]
cmd = [sys.executable, "../../experiment/tthe_collector.py", "--split", "split_eval151.json",
       "--harnesses", ",".join(second), "--workers", "6",
       "--out", "artifacts/outcomes/tthe_eval151_qwentarget.parquet"]
log("RUN collector (resume)")
r = subprocess.run(cmd, cwd=TTHE, env=ziyang_env(), capture_output=True, text=True, timeout=21600)
(ART / "p0_chain_stdout.txt").open("a", encoding="utf-8").write(r.stdout[-4000:] + "\nERR:" + r.stderr[-1500:])
log(f"collector exit={r.returncode}")

# restore GLM config + cache; archive qwen cache
cfg.write_text(cfg_bak.read_text(encoding="utf-8"), encoding="utf-8")
shutil.copy(qcache, ART / "solver_cache.qwentarget.archive.json")
if cache.with_suffix(".tmp_glm_restore").exists():
    cache.with_suffix(".tmp_glm_restore").rename(cache)
else:
    shutil.copy(cache_glm_bak, cache)
log("config + GLM cache restored; qwen cache archived")
log("STAGE 6 RESUME COMPLETE")
