"""Generate the frozen WP-1R/WP-2R acquisition configs (no secrets).

Emits four config JSONs under artifacts/wp1r_20260915/configs/:
  eval_real   : panel (8 drawn members + bare) x 400 eval tasks x repeats 1-3
  eval_clone  : 9 same-code bare clone slots x 400 eval tasks x repeats 1-3
  dev_real    : panel x 100 dev tasks x repeats 1-3 (selector training data)
  smoke       : tiny pilot config (dev section, bare only, 1 repeat, 3 tasks)

Solver settings mirror external/TTHE/config.yaml (GLM-5.3-Flash,
llmapi.paratera.com/v1, temperature per frozen member source, thinking none).
The API key is never written here; the collector reads PARATERA_API_KEY from
the environment at launch.
"""
from __future__ import annotations

import collections
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/wp1r_20260915/configs'
SPLIT = ROOT / 'artifacts/gsm8k_audit/math500_split.json'
PROTOCOL = ROOT / 'review-stage/REAL_EVIDENCE_PROTOCOL_V1.md'
PANEL_DRAW = ROOT / 'review-stage/WP1R_PANEL_DRAW.json'
CLONE_SLOTS = ROOT / 'review-stage/WP1R_CLONE_SLOTS.json'

SOLVER = {'base_url': 'https://llmapi.paratera.com/v1',
          'model': 'GLM-5.3-Flash',
          'thinking_style': 'none',
          'temperature_override': None,
          'max_tokens': 32000,
          'timeout_seconds': 300,
          'status_retries': 2,
          'retry_delay_seconds': 5}

MAX_PROVIDER_ATTEMPTS = 45000


def call_stats():
    """Frozen repeat-0 logical-call statistics per member id.

    Generated members come from run_math500.jsonl; bare from
    run_bare_math500.jsonl; clone slots inherit the bare statistics because
    they execute the identical frozen bare source.
    """
    stats = {}
    recs = [json.loads(line)
            for line in (ROOT / 'artifacts/gsm8k_audit/run_math500.jsonl')
            .read_text(encoding='utf-8').splitlines()]
    calls = collections.defaultdict(list)
    for r in recs:
        calls[r['harness_id']].append(r['n_llm_calls'])
    stats.update({h: statistics.mean(v) for h, v in calls.items()})
    bare = [json.loads(line)
            for line in (ROOT / 'artifacts/gsm8k_audit/run_bare_math500.jsonl')
            .read_text(encoding='utf-8').splitlines()]
    bare_mean = statistics.mean(r['n_llm_calls'] for r in bare)
    stats['bare'] = bare_mean
    for i in range(1, 10):
        stats[f'clone-c{i}'] = bare_mean
    return stats


def panel_members():
    draw = json.loads(PANEL_DRAW.read_text(encoding='utf-8'))
    members = []
    for entry in draw['panel']:
        mid, basis = (entry if isinstance(entry, list) else (entry, 'drawn'))
        members.append({'id': mid, 'source': f'experiment/gsm8k/agents/{mid}.py',
                        'basis': basis})
    return members


def clone_members():
    spec = json.loads(CLONE_SLOTS.read_text(encoding='utf-8'))
    return [{'id': e[0], 'source': spec['source'], 'basis': e[1]}
            for e in spec['panel']]


def base_config(acquisition_id, section, members, panel_draw_path, repeats,
                concurrency, output):
    return {
        'acquisition_id': acquisition_id,
        'protocol_path': str(PROTOCOL.relative_to(ROOT)),
        'cache_mode': 'off',
        'section': section,
        'split_path': str(SPLIT.relative_to(ROOT)),
        'schedule_salt': f'{acquisition_id}-schedule',
        'panel_draw_path': str(panel_draw_path.relative_to(ROOT)),
        'repeats': repeats,
        'harnesses': members,
        'call_stats': call_stats(),
        'solver': dict(SOLVER),
        'resource_budget': None,
        'api_key_env': 'PARATERA_API_KEY',
        'worker_wall_seconds': 1800,
        'drain_seconds': 120,
        'concurrency': concurrency,
        'max_provider_attempts': MAX_PROVIDER_ATTEMPTS,
        'global_budget_path': 'artifacts/wp1r_20260915/global_budget.json',
        'dataset_root': 'external/data/bird/dev_20240627',
        'output': output,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    panel = panel_members()
    clones = clone_members()
    configs = {
        'eval_real.json': base_config(
            'wp1r-eval-real-v1', 'eval', panel, PANEL_DRAW, [1, 2, 3], 2,
            'artifacts/wp1r_20260915/eval_real'),
        'eval_clone.json': base_config(
            'wp1r-eval-clone-v1', 'eval', clones, CLONE_SLOTS, [1, 2, 3], 2,
            'artifacts/wp1r_20260915/eval_clone'),
        'dev_real.json': base_config(
            'wp1r-dev-real-v1', 'dev', panel, PANEL_DRAW, [1, 2, 3], 2,
            'artifacts/wp1r_20260915/dev_real'),
    }
    for name, cfg in configs.items():
        path = OUT / name
        path.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding='utf-8')
        print(f'wrote {path.relative_to(ROOT)}: {len(cfg["harnesses"])} members x '
              f'{len(cfg["repeats"])} repeats, section={cfg["section"]}')


if __name__ == '__main__':
    main()
