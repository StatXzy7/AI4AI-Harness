"""Versioned fixed-three-attempt builder acquisition, separate from all admission.

The SQLite ledger retains full HTTP response bytes before code extraction. This
entry point never imports candidates, invokes a gate, or evaluates benchmark
tasks. Live use requires a separately reviewed frozen plan and provider budget.
"""
from __future__ import annotations

import argparse
import ast
import base64
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import uuid

import httpx

from experiment.revision.code_responses import extract_python
from experiment.revision.fresh_runtime import RunStore, canonical

ROOT = Path(__file__).resolve().parents[2]


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(config):
    """Resolve a reviewable plan without keys, clients or network access."""
    config = json.loads(canonical(config))
    if config['status'] not in ('DRAFT', 'FROZEN') or not config['pool_id']:
        raise ValueError('explicit pool identity and DRAFT/FROZEN status required')
    settings = config['builder']
    url = httpx.URL(settings['base_url'])
    if url.scheme not in ('http', 'https') or url.username or url.password or url.query or url.fragment:
        raise ValueError('base_url must be an HTTP endpoint without embedded credentials')
    if (not settings['model'] or type(settings['max_tokens']) is not int or settings['max_tokens'] < 1
            or settings['timeout_seconds'] <= 0 or not 0 <= settings['temperature'] <= 2):
        raise ValueError('invalid builder request settings')
    slots = config['slots']
    if any(type(slot.get('attempt_index')) is not int for slot in slots):
        raise ValueError('explicit attempt_index required')
    if not slots or len({slot['id'] for slot in slots}) != len(slots):
        raise ValueError('nonempty distinct slots required')
    for slot in slots:
        if slot['generation_condition'] not in ('free', 'forced'):
            raise ValueError('generation condition must be free or forced, not an admission arm')
        if len(slot['seeds']) != 1 or any(type(seed) is not int for seed in slot['seeds']):
            raise ValueError('each slot must specify exactly three integer seeds')
        if (not slot['messages'] or any(m.get('role') not in ('system', 'user')
                                       or not isinstance(m.get('content'), str) for m in slot['messages'])):
            raise ValueError('slot messages must be fixed system/user text')
    sources = [Path(__file__), ROOT / 'experiment/revision/code_responses.py',
               ROOT / 'experiment/revision/fresh_runtime.py', ROOT / config['protocol_path']]
    bindings = {str(path.resolve()): file_hash(path) for path in sources}
    return dict(version='common-pool-v1', config=config, bindings=bindings,
                planned_attempts=len(slots), cache_mode='off', status_retries=0,
                interpretation='complete pool requires all planned attempts and known token usage; no admission')


def validate_bindings(store, manifest):
    changed = [path for path, value in manifest['bindings'].items()
               if not Path(path).is_file() or file_hash(path) != value]
    if changed:
        store.event('run_invalid', reason='bound_source_or_protocol_changed', paths=changed)
        raise RuntimeError('bound source/protocol changed; pool is invalid')


def usage_known(usage):
    return (isinstance(usage, dict) and
            all(type(usage.get(k)) is int and usage[k] >= 0
                for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')) and
            usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'])


def publish(path, value):
    """Publish a complete deterministic export; ledger remains authoritative."""
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('existing export differs from the ledger')
        return
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path)
    temporary.unlink()


def collect(config, api_key, *, transport=None):
    manifest = prepare(config)
    config = manifest['config']
    if config['status'] != 'FROZEN':
        raise ValueError('DRAFT plans cannot issue requests')
    if not api_key:
        raise ValueError('provider key required')
    output = ROOT / config['output']
    settings = config['builder']
    endpoint = settings['base_url'].rstrip('/') + '/chat/completions'
    with RunStore(output, manifest) as store, httpx.Client(
            transport=transport, timeout=settings['timeout_seconds'], trust_env=False,
            follow_redirects=False) as client:
        for slot in config['slots']:
            for seed in slot['seeds']:
                attempt_index = slot['attempt_index']
                validate_bindings(store, manifest)
                identity = dict(slot=slot.get('identity_slot', slot['id']), attempt=attempt_index, seed=seed)
                key, started = store.begin(identity)
                if not started:
                    continue
                request = dict(model=settings['model'], messages=slot['messages'], seed=seed,
                               n=1, temperature=settings['temperature'], max_tokens=settings['max_tokens'])
                logical = store.event('logical_start', task=key, n=1, request=request, cache_hit=False)
                http = store.event('http_start', task=key, logical=logical, request=request, url=endpoint)
                try:
                    with client.stream('POST', endpoint, json=request,
                                       headers={'Authorization': 'Bearer ' + api_key,
                                                'Accept-Encoding': 'identity'}) as response:
                        body = b''.join(response.iter_raw())
                except Exception as exc:
                    store.event('http_unknown', task=key, attempt=http, error_type=type(exc).__name__)
                    raise RuntimeError('provider completion/cost unknown; no automatic retry or continuation') from exc
                # The raw response commit precedes all JSON parsing and code extraction.
                body_hash = hashlib.sha256(body).hexdigest()
                store.event('builder_response_bytes', task=key, attempt=http,
                            status=response.status_code, body_base64=base64.b64encode(body).decode('ascii'),
                            body_sha256=body_hash, request_id=response.headers.get('x-request-id'),
                            content_encoding=response.headers.get('content-encoding'),
                            content_type=response.headers.get('content-type'))
                validate_bindings(store, manifest)
                try:
                    encoding = response.headers.get('content-encoding', 'identity').lower().strip()
                    if encoding not in ('identity', 'gzip', 'deflate'):
                        raise ValueError('unsupported content encoding; original body retained')
                    decoded = httpx.Response(200, headers={'content-encoding': encoding}, content=body).content
                    payload = json.loads(decoded)
                except (ValueError, UnicodeError, httpx.DecodingError):
                    payload = None
                usage = payload.get('usage') if isinstance(payload, dict) else None
                store.event('http_end', task=key, attempt=http, status=response.status_code,
                            usage=usage if usage_known(usage) else None, response_sha256=body_hash)
                if response.status_code != 200 or not isinstance(payload, dict):
                    raise RuntimeError('provider response unusable; retained bytes and stopped pool')
                choices = payload.get('choices')
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                    raise RuntimeError('unexpected builder response shape; retained bytes and stopped pool')
                choice = choices[0]
                message = choice.get('message')
                if (not isinstance(message, dict) or 'content' not in message
                        or not isinstance(message['content'], (str, type(None)))):
                    raise RuntimeError('unexpected builder message shape; retained bytes and stopped pool')
                text = message['content']
                extraction = extract_python(text)
                syntax_error = None
                if extraction.code is not None:
                    try:
                        ast.parse(extraction.code)
                    except SyntaxError as exc:
                        syntax_error = dict(message=exc.msg, line=exc.lineno, offset=exc.offset)
                result = dict(identity=identity, generation_condition=slot['generation_condition'],
                              strategy=slot.get('strategy'), response_sha256=body_hash,
                              reported_model=payload.get('model'), response_id=payload.get('id'),
                              finish_reason=choice.get('finish_reason'), message=text,
                              extraction=asdict(extraction), syntax_error=syntax_error,
                              code_sha256=hashlib.sha256(extraction.code.encode('utf-8')).hexdigest()
                              if extraction.code is not None else None, usage=usage,
                              admission='not_evaluated')
                store.event('candidate_extracted', task=key, result=result)
                if not usage_known(usage):
                    raise RuntimeError('usage unknown or inconsistent; response and extraction retained, pool stopped')
                store.event('logical_end', task=key, logical=logical)
                store.finish(key, result)
        validate_bindings(store, manifest)
        snapshot = store.snapshot()
        if len(snapshot['tasks']) != manifest['planned_attempts'] or any(t['result'] is None for t in snapshot['tasks']):
            raise RuntimeError('not all planned attempts are complete')
        publish(output / 'pool.json', snapshot)
        publish(output / 'POOL_COMPLETE.json', dict(pool_sha256=file_hash(output / 'pool.json'),
                                                  planned_attempts=manifest['planned_attempts'],
                                                  run_id=store.run_id, admission='not_evaluated'))
        return snapshot


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    if args.prepare_only:
        print(json.dumps(prepare(config), ensure_ascii=False, indent=2))
    else:
        collect(config, os.environ.get(config['api_key_env']))
