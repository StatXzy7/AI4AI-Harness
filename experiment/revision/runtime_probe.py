"""Exercise the real local collection stack against a loopback-only fake provider.

No production config, BIRD data, credentials, or upstream source is modified.
This records current behavior (including defects); it does not certify a fresh
provider run or implement the future experimental runtime.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]


def worker(folder):
    """Runs only in a fresh interpreter so bridge's import-time state cannot leak."""
    folder = Path(folder)
    records = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                number = len(records) + 1
                retry_prompt = request['messages'][-1]['content'] == 'SDK_RETRY'
                fail = retry_prompt and not any(r['case'] == 'retry' for r in records)
                usage = {'prompt_tokens': 11, 'completion_tokens': 7, 'total_tokens': 18}
                records.append({'request_index': number, 'path': self.path,
                                'case': 'retry' if retry_prompt else 'ordinary',
                                'request': request, 'status': 429 if fail else 200,
                                'response_id': None if fail else f'fixture-{number}',
                                'usage': None if fail else usage})
            if fail:
                payload = {'error': {'message': 'fixture retry', 'type': 'rate_limit_error'}}
            else:
                payload = {'id': f'fixture-{number}', 'object': 'chat.completion',
                           'created': 1, 'model': request['model'], 'usage': usage,
                           'choices': [{'index': 0, 'finish_reason': 'stop',
                                        'message': {'role': 'assistant', 'content':
                                            f'```sql\nSELECT count(*) FROM ledger -- reply {number}\n```'}}]}
            body = json.dumps(payload).encode('utf-8')
            self.send_response(429 if fail else 200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Explicitly remove inherited endpoint/config/temperature overrides.
        for key in list(os.environ):
            if key.startswith(('SOLVER_', 'SQL_SOLVER_', 'BIRD_', 'ASE_')):
                del os.environ[key]
        os.environ['NO_PROXY'] = os.environ['no_proxy'] = '127.0.0.1,localhost'
        os.environ['REVISION_DUMMY_KEY'] = 'loopback-fixture-not-a-secret'
        os.environ['SQL_SOLVER_CACHE'] = str(folder / 'cache.json')
        config = {'llm': {'provider': 'openai',
                         'base_url': f'http://127.0.0.1:{server.server_port}/v1',
                         'api_key_env': 'REVISION_DUMMY_KEY',
                         'solver_model': 'fixture-model', 'controller_model': 'fixture-model',
                         'thinking_style': 'none', 'request_timeout': 5},
                  'dataset': {'name': 'bird', 'bird_root': str(folder)},
                  'output_dir': str(folder / 'runs')}
        config_path = folder / 'config.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        os.environ['TTHE_CONFIG'] = str(config_path)  # JSON is also valid YAML.
        database_dir = folder / 'dev_databases' / 'fixture'
        database_dir.mkdir(parents=True)
        with sqlite3.connect(database_dir / 'fixture.sqlite') as conn:
            conn.execute('CREATE TABLE ledger (id INTEGER, label TEXT)')
            conn.executemany('INSERT INTO ledger VALUES (?,?)', [(1, '甲'), (2, '乙'), (3, '丙')])
        (folder / 'dev.json').write_text(json.dumps([
            {'db_id': 'fixture', 'question': 'How many ledger entries?',
             'SQL': 'SELECT count(*) FROM ledger'}]), encoding='utf-8')
        split_dir = folder / 'experiment/phase2'
        split_dir.mkdir(parents=True)
        (split_dir / 'fixture.json').write_text(
            json.dumps({'by_db': {'fixture': [0]}}), encoding='utf-8')

        sys.path.insert(0, str(ROOT / 'external/TTHE'))
        sys.path.insert(0, str(ROOT / 'experiment'))
        from phase2 import collect, official_scorer
        # Route only data/output roots; execute original collector and scoring code.
        collect.ROOT = folder
        official_scorer.BIRD_ROOT = folder
        official_scorer.DB_DIR = folder / 'dev_databases'
        output = folder / 'collected.jsonl'
        collector_cases = []
        for name, repeat, cache_off in [('first', 0, False), ('resume', 0, False),
                                       ('repeat_cached', 1, False),
                                       ('fresh_2', 2, True), ('fresh_3', 3, True),
                                       ('resume_mode_switch', 0, True)]:
            before = len(records)
            sys.argv = ['collect', '--split', 'fixture', '--harnesses', 'bare',
                        '--target', 'fixture-model', '--workers', '1',
                        '--repeat', str(repeat), '--out', str(output)]
            if cache_off:
                sys.argv.append('--no-cache')
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                collect.main()
            collector_cases.append({'case': name, 'repeat': repeat,
                                    'http_requests': len(records) - before,
                                    'stdout': stdout.getvalue().replace(str(folder), '<temporary>')})
        rows = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]

        from text_to_sql import bridge
        from text_to_sql.agents.bare import BareHarness
        from ase.solver_cache import SolverCache
        db = bridge.get_db('fixture')
        # Use a new real cache object: no bypass, no mutation of upstream implementation.
        bridge._CACHE = SolverCache(str(folder / 'pending_cache.json'), flush_interval=1e6)
        h1, h2 = BareHarness(db), BareHarness(db)
        pending = []
        for name, harness in [('first_seq0', h1), ('first_seq1', h1),
                              ('clone_seq0', h2), ('clone_seq1', h2)]:
            before = len(records)
            answer = harness.llm('PENDING_CACHE')
            pending.append({'case': name, 'http_requests': len(records) - before,
                            'answer': answer})
        bridge._CACHE.flush()

        # Uncached requests preserve the collector's exact bypass behavior.
        bridge._CACHE.get_or_call = lambda parts, produce: produce()
        samples = BareHarness(db)
        before = len(records)
        outputs = samples.llm('MULTI_SAMPLE', n=3)
        multiple = {'logical_trace_calls': len(samples._trace), 'outputs': outputs,
                    'http_requests': len(records) - before, 'trace': samples._trace}
        before = len(records)
        retry = BareHarness(db)
        # Observe the real SDK method boundary while preserving its transport/retry behavior.
        completions = bridge._LLM._client.chat.completions
        original_create = completions.create
        create_calls = []
        def counted_create(**kwargs):
            create_calls.append(1)
            return original_create(**kwargs)
        completions.create = counted_create
        retry.llm('SDK_RETRY')
        completions.create = original_create
        retry_result = {'logical_trace_calls': len(retry._trace),
                        'sdk_create_calls': len(create_calls),
                        'http_requests': len(records) - before,
                        'statuses': [r['status'] for r in records[before:]]}
        bridge._LLM.cfg.thinking_style = 'deepseek'
        BareHarness(db).llm('THINKING_TEMPERATURE', temperature=0.7)
        thinking_request = records[-1]['request']

        # Exercise actual project judges on a synthetic database, with both divergence directions.
        judge_cases = []
        for predicted, gold in [('SELECT 1', 'SELECT 1.0'),
                                ("SELECT '1'", 'SELECT 1'),
                                ('SELECT 1 UNION ALL SELECT 1', 'SELECT 1'),
                                ('SELECT missing FROM ledger', 'SELECT 1')]:
            judge_cases.append({'prediction': predicted, 'gold': gold,
                                'official': official_scorer.official_correct('fixture', predicted, gold),
                                'legacy': int(bridge.is_correct(bridge.execute(db, predicted),
                                                               bridge.gold_result(db, gold)))})
        return {'scope': 'synthetic loopback integration, no paid API or empirical BIRD outcomes',
                'python': sys.version.split()[0],
                'packages': {k: importlib.metadata.version(k) for k in ('openai', 'PyYAML', 'httpx')},
                'collector_cases': collector_cases, 'collector_rows': rows,
                'pending_cache': pending, 'multi_sample': multiple, 'retry': retry_result,
                'thinking_request': thinking_request, 'judge_cases': judge_cases,
                'provider_ledger': records,
                'temporary_routes': ['TTHE_CONFIG', 'SQL_SOLVER_CACHE', 'collect.ROOT',
                                     'official_scorer.BIRD_ROOT', 'official_scorer.DB_DIR'],
                'observation_wrapper': 'SDK create delegates unchanged; counts method entries during retry case',
                'upstream_changes': False}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_probe():
    paths = ['experiment/revision/runtime_probe.py', 'experiment/phase2/collect.py',
             'experiment/phase2/official_scorer.py', 'external/TTHE/ase/llm.py',
             'external/TTHE/ase/solver_cache.py', 'external/TTHE/ase/db.py',
             'external/TTHE/ase/dataset.py', 'external/TTHE/text_to_sql/bridge.py',
             'external/TTHE/text_to_sql/harness_base.py',
             'external/TTHE/text_to_sql/evolve.py', 'external/TTHE/text_to_sql/agents/bare.py']
    def source_hashes():
        return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
    before = source_hashes()
    with tempfile.TemporaryDirectory(prefix='revision_runtime_') as folder:
        result_path = Path(folder) / 'result.json'
        completed = subprocess.run([sys.executable, '-m', 'experiment.revision.runtime_probe',
                                    '--worker', folder, '--out', str(result_path)],
                                   cwd=ROOT, text=True, encoding='utf-8',
                                   capture_output=True, timeout=90, check=True)
        result = json.loads(result_path.read_text(encoding='utf-8'))
        result['worker_stderr'] = completed.stderr
    after = source_hashes()
    if before != after:
        raise RuntimeError('Measured source changed during execution; discard this probe result')
    result['source_sha256'] = before
    result['source_unchanged_during_run'] = True
    result['created_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--out', type=Path,
                        default=ROOT / 'artifacts/revision_20260910/runtime_probe.json')
    args = parser.parse_args()
    result = worker(args.worker) if args.worker else run_probe()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    main()
