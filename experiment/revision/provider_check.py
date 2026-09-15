"""Provider verification + synthetic smoke for the Paratera endpoint.

Run ONLY after the G0 design gate passes. Performs the smallest possible paid
calls needed to verify: base URL path, authentication, exact model id,
parameter support (temperature / seed / max_tokens), usage accounting,
request/response ids, and returned model identity. Writes a secret-free audit
record under artifacts/wp1r_20260915/provider_audit/.

Cost bound: 6 tiny requests with max_tokens<=32 (well under 0.01 CNY at any
plausible flash-model pricing).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / 'artifacts/wp1r_20260915/provider_audit'
BASE = 'https://llmapi.paratera.com/v1'
MODEL = 'GLM-5.3-Flash'
KEY_FILES = ['experiment/.env_tthe', 'experiment/.env_tthe_ziyang']


def load_key(rel):
    for line in (ROOT / rel).read_text(encoding='utf-8').splitlines():
        name, _, value = line.partition('=')
        if name.strip() == 'PARATERA_API_KEY':
            return value.strip().strip('"').strip("'")
    return None


def audit(name, record):
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIT_DIR / f'{name}.json'
    existing = json.loads(path.read_text()) if path.exists() else []
    existing.append({'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **record})
    path.write_text(json.dumps(existing, indent=1, ensure_ascii=False), encoding='utf-8')
    return existing[-1]


def chat(client, key_name, **params):
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    body = {'model': MODEL, 'max_tokens': 32,
            'messages': [{'role': 'user', 'content': 'Reply with the single word: ok'}]}
    body.update(params)
    started = time.monotonic()
    response = client.post(f'{BASE}/chat/completions',
                           headers={'Authorization': f'Bearer {os.environ["_KEY"]}'},
                           json=body)
    elapsed = time.monotonic() - started
    try:
        payload = response.json()
    except Exception:
        payload = None
    record = {'status': response.status_code, 'elapsed_s': round(elapsed, 2),
              'request_id': response.headers.get('x-request-id'),
              'returned_model': (payload or {}).get('model'),
              'response_id': (payload or {}).get('id'),
              'usage': (payload or {}).get('usage'),
              'finish_reason': (((payload or {}).get('choices') or [{}])[0].get('finish_reason')),
              'content_head': ((((payload or {}).get('choices') or [{}])[0].get('message') or {})
                               .get('content', '') or '')[:60],
              'key_source': key_name,
              'error': None if response.status_code == 200 else response.text[:200]}
    # Durable secret-free request ledger: every attempt with full bodies and
    # response envelope (authorization headers never written).
    with open(AUDIT_DIR / 'provider_ledger.jsonl', 'a', encoding='utf-8') as fh:
        fh.write(json.dumps({'ts': time.time(), 'request_body': body,
                             'response_status': record['status'],
                             'response': payload if record['status'] == 200
                             else record['error']}, ensure_ascii=False) + '\n')
    return record


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    results = {'base': BASE, 'requested_model': MODEL, 'checks': {}}
    for rel in KEY_FILES:
        key = load_key(rel)
        if not key:
            continue
        os.environ['_KEY'] = key
        tag = Path(rel).name
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
            # 1. models list (may fail without implying the model is unavailable)
            try:
                r = client.get(f'{BASE}/models',
                               headers={'Authorization': f'Bearer {os.environ["_KEY"]}'})
                entries = r.json().get('data', []) if r.status_code == 200 else []
                ids = [e.get('id') for e in entries]
                with open(AUDIT_DIR / 'provider_ledger.jsonl', 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps({'ts': time.time(), 'request': 'GET /models',
                                         'response_status': r.status_code,
                                         'response_ids_head': ids[:20]},
                                        ensure_ascii=False) + '\n')
                results['checks'][f'models_list_{tag}'] = {
                    'status': r.status_code, 'n_models': len(ids),
                    'model_listed': MODEL in ids,
                    'request_id': r.headers.get('x-request-id')}
            except Exception as exc:
                results['checks'][f'models_list_{tag}'] = {'error': type(exc).__name__}
            # 2. minimal chat: temperature support
            results['checks'][f'chat_temp0_{tag}'] = chat(client, tag, temperature=0.0)
            # 3. seed parameter acceptance
            results['checks'][f'chat_seed_{tag}'] = chat(client, tag, temperature=0.0, seed=20260915)
            # 4. explicit max_tokens=1 acceptance
            results['checks'][f'chat_maxtok1_{tag}'] = chat(client, tag, temperature=0.0, max_tokens=1)
        break  # first working key file wins; audit records which
    os.environ.pop('_KEY', None)
    ok = any(str(v.get('status')) == '200' and v.get('usage')
             for k, v in results['checks'].items() if k.startswith('chat_temp0'))
    results['smoke_ok'] = bool(ok)
    out = AUDIT_DIR / 'provider_check_summary.json'
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in results.items() if k != 'checks'}, ensure_ascii=False))
    for k, v in results['checks'].items():
        print(f"  {k}: status={v.get('status')} usage={v.get('usage')} "
              f"req_id={v.get('request_id')} model={v.get('returned_model')} err={v.get('error')}")
    return 0 if results['smoke_ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
