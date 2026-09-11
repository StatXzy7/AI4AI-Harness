"""Behavioral tests of the new acquisition, using real HTTP/SDK and temporary data."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from experiment.revision.fresh_runtime import (FreshSolver, ResourceBudget, RunStore,
                                                SolverSettings)
from experiment.revision.fresh_collect import ROOT, fetch_readonly, file_hash, validate_inputs


@contextmanager
def provider(delay_duplicate=False):
    calls = []
    lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            prompt = request['messages'][-1]['content']
            with lock:
                retry = prompt == 'RETRY' and not any(c['prompt'] == prompt for c in calls)
                delay = delay_duplicate and any(c['prompt'] == prompt for c in calls)
                calls.append({'prompt': prompt, 'request': request})
                index = len(calls)
            if prompt == 'TIMEOUT':
                time.sleep(0.3)
            if delay:
                time.sleep(1.2)
            body = {'id': f'response-{index}', 'object': 'chat.completion', 'created': 1,
                    'model': request['model'], 'choices': [{'index': 0, 'finish_reason': 'stop',
                    'message': {'role': 'assistant', 'content':
                                f'SELECT count(*) FROM ledger -- response {index}'}}]}
            if prompt != 'NO_USAGE':
                body['usage'] = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}
            if retry:
                body = {'error': {'message': 'fixture retry', 'type': 'rate_limit_error'}}
            raw = json.dumps(body).encode('utf-8')
            self.send_response(429 if retry else 200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('x-request-id', f'http-{index}')
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Deliberately timed-out client; server may still finish.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class FreshRuntimeTests(unittest.TestCase):
    def test_identity_changes_rejected_and_pending_request_cannot_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = {'cache_mode': 'off', 'code': 'a', 'solver': {'model': 'm'}, 'tasks': 't'}
            with RunStore(folder, manifest) as store:
                key, _ = store.begin({'repeat': 0})
                store.finish(key, {'correct': 1})
            for field in manifest:
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'identity'):
                    with RunStore(folder, {**manifest, field: 'changed'}):
                        pass
            with RunStore(folder, manifest) as store:
                self.assertFalse(store.begin({'repeat': 0})[1])
                store.begin({'repeat': 1})
            with self.assertRaisesRegex(RuntimeError, 'Unfinished'):
                with RunStore(folder, manifest):
                    pass

    def test_second_writer_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, RunStore(folder, {}) as store:
            with self.assertRaisesRegex(RuntimeError, 'writer'):
                with RunStore(folder, {}):
                    pass
            self.assertEqual(store.snapshot()['tasks'], [])

    def test_late_thread_cannot_be_attributed_to_another_task(self):
        with provider() as (url, calls), tempfile.TemporaryDirectory() as folder:
            settings = SolverSettings(url, 'fixture')
            manifest = {'solver': asdict(settings), 'cache_mode': 'off'}
            with RunStore(folder, manifest) as store:
                solver = FreshSolver(store, settings, 'dummy')
                wake = threading.Event()
                errors = []
                def late():
                    wake.wait()
                    try:
                        solver('LATE')
                    except RuntimeError as exc:
                        errors.append(str(exc))
                try:
                    key, _ = store.begin({'task': 'A'})
                    with solver.bind(key):
                        thread = threading.Thread(target=late)
                        thread.start()
                    with self.assertRaisesRegex(RuntimeError, 'immutable'):
                        with solver.bind('B'):
                            pass
                    wake.set()
                    thread.join()
                    self.assertEqual(len(calls), 0)
                    self.assertTrue(errors)
                    with self.assertRaisesRegex(RuntimeError, 'invalid'):
                        store.finish(key, {})
                finally:
                    wake.set()
                    thread.join()
                    solver.close()

    def test_restoring_changed_input_cannot_resurrect_invalid_completed_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'data'
            source.write_bytes(b'original')
            expected = {source: file_hash(source)}
            with RunStore(Path(folder) / 'run', {}) as store:
                key, _ = store.begin({})
                store.finish(key, {})
                source.write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError, 'invalid'):
                    validate_inputs(store, expected)
                source.write_bytes(b'original')
            with self.assertRaisesRegex(RuntimeError, 'invalid'):
                with RunStore(Path(folder) / 'run', {}):
                    pass

    def test_fresh_samples_threads_retry_usage_and_temperature_are_recorded(self):
        with provider() as (url, calls), tempfile.TemporaryDirectory() as folder:
            settings = SolverSettings(url, 'fixture', status_retries=1, retry_delay_seconds=0)
            with RunStore(folder, {'solver': asdict(settings), 'cache_mode': 'off'}) as store:
                solver = FreshSolver(store, settings, 'dummy-local-only')
                try:
                    key, _ = store.begin({'repeat': 0})
                    with solver.bind(key):
                        first = solver('SAME')
                        second = solver('SAME')
                        self.assertNotEqual(first, second)
                        self.assertEqual(len(set(solver('N3', n=3))), 3)
                        # Real harnesses can call llm from their own joined pools.
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            self.assertEqual(len(list(pool.map(solver, ['THREAD', 'THREAD']))), 2)
                        solver('RETRY')
                    store.finish(key, {'ok': True})
                    snapshot = store.snapshot()
                    account = snapshot['tasks'][0]['result']['accounting']
                    self.assertEqual(account['logical_calls'], 6)
                    self.assertEqual(account['requested_samples'], 8)
                    self.assertEqual(account['http_attempts'], 9)
                    self.assertEqual(account['known_total_tokens'], 40)
                    self.assertEqual(account['responses_missing_usage'], 1)
                    self.assertIsNone(account['total_tokens'])  # The 429 has unknown usage.
                    self.assertEqual(len(calls), 9)
                    ends = [e for e in snapshot['events'] if e['kind'] == 'http_end']
                    self.assertTrue(all(e['request_id'] for e in ends))
                finally:
                    solver.close()

    def test_per_cell_resource_budget_rejects_before_provider_request(self):
        with provider() as (url, calls), tempfile.TemporaryDirectory() as folder:
            settings = SolverSettings(url, 'fixture')
            budget = ResourceBudget(max_logical_calls=1, max_requested_samples=1,
                                   max_output_tokens=settings.max_tokens)
            manifest = {'solver': asdict(settings), 'cache_mode': 'off',
                        'resource_budget': asdict(budget)}
            with RunStore(folder, manifest) as store:
                solver = FreshSolver(store, settings, 'dummy', budget)
                try:
                    key, _ = store.begin({'task': 'budgeted'})
                    with solver.bind(key):
                        solver('FIRST')
                        with self.assertRaisesRegex(RuntimeError, 'resource budget'):
                            solver('SECOND')
                    with self.assertRaisesRegex(RuntimeError, 'budget-rejected'):
                        store.finish(key, {'ok': True})
                    snapshot = store.snapshot()
                    self.assertEqual(len(calls), 1)
                    self.assertIsNone(snapshot['tasks'][0]['result'])
                    rejected = [e for e in snapshot['events']
                                if e['kind'] == 'resource_budget_rejected']
                    self.assertEqual(len(rejected), 1)
                    self.assertEqual(rejected[0]['limits'], asdict(budget))
                finally:
                    solver.close()

    def test_resource_budget_is_bound_to_manifest(self):
        with provider() as (url, _), tempfile.TemporaryDirectory() as folder:
            settings = SolverSettings(url, 'fixture')
            manifest = {'solver': asdict(settings), 'cache_mode': 'off',
                        'resource_budget': asdict(ResourceBudget(2, 2, 64000))}
            with RunStore(folder, manifest) as store:
                with self.assertRaisesRegex(ValueError, 'Resource budget'):
                    FreshSolver(store, settings, 'dummy', ResourceBudget(1, 1, 32000))

    def test_missing_usage_is_unknown_and_thinking_temperature_is_explicit(self):
        with provider() as (url, _), tempfile.TemporaryDirectory() as folder:
            settings = SolverSettings(url, 'fixture', thinking_style='deepseek')
            with RunStore(folder, {'solver': asdict(settings), 'cache_mode': 'off'}) as store:
                solver = FreshSolver(store, settings, 'dummy')
                try:
                    key, _ = store.begin({})
                    with solver.bind(key):
                        solver('NO_USAGE', temperature=0.7)
                    store.finish(key, {})
                    snapshot = store.snapshot()
                    event = next(e for e in snapshot['events'] if e['kind'] == 'logical_start')
                    self.assertEqual(event['requested_temperature'], 0.7)
                    self.assertIsNone(event['transmitted_temperature'])
                    wire = next(e for e in snapshot['events'] if e['kind'] == 'http_start')['request']
                    self.assertNotIn('temperature', wire)
                    self.assertEqual(wire['thinking'], {'type': 'enabled'})
                    self.assertIsNone(snapshot['tasks'][0]['result']['accounting']['total_tokens'])
                finally:
                    solver.close()

    def test_caught_timeout_fallback_does_not_complete_or_resume(self):
        with provider() as (url, calls), tempfile.TemporaryDirectory() as folder:
            settings = SolverSettings(url, 'fixture', timeout_seconds=0.05, status_retries=2)
            manifest = {'solver': asdict(settings), 'cache_mode': 'off'}
            with RunStore(folder, manifest) as store:
                solver = FreshSolver(store, settings, 'dummy')
                try:
                    key, _ = store.begin({})
                    with solver.bind(key):
                        try:
                            solver('TIMEOUT')
                        except Exception:
                            fallback_sql = 'SELECT 1'
                    with self.assertRaisesRegex(RuntimeError, 'unknown'):
                        store.finish(key, {'final_sql': fallback_sql, 'correct': 1})
                    self.assertEqual(len(calls), 1)  # No automatic retry of unknown completion.
                    self.assertTrue(any(e['kind'] == 'http_unknown' for e in store.snapshot()['events']))
                finally:
                    solver.close()
            with self.assertRaisesRegex(RuntimeError, 'Unfinished'):
                with RunStore(folder, manifest):
                    pass

    def test_collector_real_bare_clones_cross_process_resume_and_judge(self):
        with provider() as (url, calls), tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            db_dir = folder / 'dev_databases/fixture'
            db_dir.mkdir(parents=True)
            db_path = db_dir / 'fixture.sqlite'
            conn = sqlite3.connect(db_path)
            conn.execute('CREATE TABLE ledger (id INTEGER)')
            conn.executemany('INSERT INTO ledger VALUES (?)', [(1,), (2,)])
            conn.commit()
            conn.close()
            (folder / 'dev.json').write_text(json.dumps([{'db_id': 'fixture', 'question': 'How many entries?',
                                                         'SQL': 'SELECT count(*) FROM ledger'}]), encoding='utf-8')
            split = folder / 'split.json'
            split.write_text(json.dumps({'by_db': {'fixture': [0]}}), encoding='utf-8')
            protocol = folder / 'protocol.txt'
            protocol.write_text('Synthetic development fixture, not a frozen research protocol.', encoding='utf-8')
            config = {'acquisition_id': 'fixture', 'cache_mode': 'off',
                      'solver': asdict(SolverSettings(url, 'fixture')), 'api_key_env': 'FIXTURE_KEY',
                      'dataset_root': str(folder), 'split_path': str(split), 'protocol_path': str(protocol),
                      'repeats': [0, 1], 'harnesses': [
                          {'id': h, 'source': 'external/TTHE/text_to_sql/agents/bare.py'} for h in ['bare', 'clone']],
                      'output': str(folder / 'output')}
            config_path = folder / 'config.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            cmd = [sys.executable, '-m', 'experiment.revision.fresh_collect', '--config', str(config_path)]
            env = {**os.environ, 'FIXTURE_KEY': 'dummy'}
            first = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=40)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(len(calls), 4)
            snapshot = json.loads((folder / 'output/snapshot.json').read_text(encoding='utf-8'))
            self.assertEqual(len(snapshot['tasks']), 4)
            self.assertTrue(all(t['result']['official_correct'] == 1 for t in snapshot['tasks']))
            self.assertEqual(len({t['result']['final_sql'] for t in snapshot['tasks']}), 4)
            second = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=40)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(len(calls), 4)
            config['solver']['max_tokens'] += 1
            config_path.write_text(json.dumps(config), encoding='utf-8')
            third = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=40)
            self.assertNotEqual(third.returncode, 0)
            self.assertIn('identity changed', third.stderr)
            self.assertEqual(len(calls), 4)
            self.assertEqual(set(fetch_readonly(db_path, 'SELECT 1')), set(fetch_readonly(db_path, 'SELECT 1.0')))
            self.assertNotEqual(set(fetch_readonly(db_path, "SELECT '1'")), set(fetch_readonly(db_path, 'SELECT 1')))
            self.assertIsNone(fetch_readonly(db_path, 'DROP TABLE ledger'))
            with provider(delay_duplicate=True) as (race_url, race_calls):
                config['solver']['base_url'] = race_url
                config['harnesses'] = [{'id': 'race', 'source':
                    'external/TTHE/text_to_sql/agents/cand_bird_g1_b0r1_g1.py'}]
                config['repeats'] = [0]
                config['output'] = str(folder / 'race_output')
                config_path.write_text(json.dumps(config), encoding='utf-8')
                race = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                                      encoding='utf-8', timeout=40)
                self.assertNotEqual(race.returncode, 0)
                self.assertIn('unjoined threads', race.stderr)
                self.assertEqual(len(race_calls), 2)
                resumed = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                                         encoding='utf-8', timeout=40)
                self.assertNotEqual(resumed.returncode, 0)
                self.assertIn('marked invalid', resumed.stderr)
                self.assertEqual(len(race_calls), 2)


if __name__ == '__main__':
    unittest.main()
