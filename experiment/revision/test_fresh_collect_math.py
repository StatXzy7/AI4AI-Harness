"""Offline loopback tests for the MATH fresh acquisition collector.

Mirrors test_isolated_collect.py: a local HTTP provider stands in for the
endpoint; no paid call is ever made. Covers: worker loading from manifest
source path (clone identity), judge result and accounting, the global
provider-attempt budget, sliding-window failure policy, and shard
partitioning of the interleaved schedule.
"""
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from experiment.revision.fresh_collect_math import (GlobalBudget, collect,
                                                    math_tasks, prepare,
                                                    worker)
from experiment.revision.isolated_collect import read_ledger

BARE_SOURCE = 'experiment/gsm8k/agents/bare.py'


@contextmanager
def provider(answer='#### 42', fail_status=None):
    calls = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                index = len(calls) + 1
                calls.append({'body': body})
            if fail_status is not None:
                self.send_response(fail_status)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            payload = {'id': f'resp-{index}', 'object': 'chat.completion', 'created': 1,
                       'model': body['model'],
                       'usage': {'prompt_tokens': 10, 'completion_tokens': 5,
                                 'total_tokens': 15},
                       'choices': [{'index': 0, 'finish_reason': 'stop',
                                    'message': {'role': 'assistant', 'content': answer}}]}
            raw = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextmanager
def fixture(harness_ids=('bare',), repeats=(1,), concurrency=1, answer='#### 42',
            fail_status=None, max_attempts=100000, members=None):
    with tempfile.TemporaryDirectory(prefix='math_fresh_test_') as temporary:
        folder = Path(temporary)
        (folder / 'bird/dev_databases/fixture').mkdir(parents=True)
        conn = sqlite3.connect(folder / 'bird/dev_databases/fixture/fixture.sqlite')
        conn.execute('CREATE TABLE t (id INTEGER)')
        conn.commit()
        conn.close()
        (folder / 'bird/dev.json').write_text('[]', encoding='utf-8')
        tasks = [{'question': f'What is 6*7? ({i})', 'gold': '42', 'subject': 'x',
                  'level': '1'} for i in range(100)]
        (folder / 'split.json').write_text(json.dumps({'tasks': tasks}), encoding='utf-8')
        members = members or [
            {'id': hid, 'source': BARE_SOURCE, 'mechanism': 'test'} for hid in harness_ids]
        ids = sorted(m['id'] for m in members)
        (folder / 'draw.json').write_text(json.dumps(
            {'salt': 'test-salt-20260915', 'panel': ids, 'eligible': ids}), encoding='utf-8')
        config = {
            'acquisition_id': 'math-fresh-test-loopback',
            'protocol_path': 'review-stage/REAL_EVIDENCE_PROTOCOL_V1.md',
            'cache_mode': 'off',
            'section': 'dev',
            'split_path': str(folder / 'split.json'),
            'schedule_salt': 'test-salt-20260915',
            'panel_draw_path': str(folder / 'draw.json'),
            'repeats': list(repeats),
            'harnesses': members,
            'call_stats': {h['id']: 1.0 for h in members},
            'solver': {'base_url': None, 'model': 'GLM-5.3-Flash', 'thinking_style': 'none',
                       'temperature_override': None, 'max_tokens': 512,
                       'timeout_seconds': 30, 'status_retries': 0,
                       'retry_delay_seconds': 0.1},
            'resource_budget': None,
            'api_key_env': 'MATH_TEST_KEY',
            'worker_wall_seconds': 120, 'drain_seconds': 20,
            'concurrency': concurrency,
            'max_provider_attempts': max_attempts,
            'dataset_root': str(folder / 'bird'),
            'output': str(folder / 'acq'),
        }
        with provider(answer=answer, fail_status=fail_status) as (url, calls):
            config['solver']['base_url'] = url
            os.environ['MATH_TEST_KEY'] = 'test-key-not-a-secret'
            yield folder, config, calls


class TestMathTasks(unittest.TestCase):
    def test_dev_slice_is_first_100(self):
        tasks = math_tasks(Path('artifacts/gsm8k_audit/math500_split.json'), 'dev')
        self.assertEqual(len(tasks), 100)
        self.assertTrue(all(t['id'].startswith('math500_split#') for t in tasks))

    def test_eval_slice_is_last_400(self):
        tasks = math_tasks(Path('artifacts/gsm8k_audit/math500_split.json'), 'eval')
        self.assertEqual(len(tasks), 400)
        ids = {t['id'] for t in tasks}
        self.assertNotIn('math500_split#0', ids)
        self.assertIn('math500_split#100', ids)


class TestPanelBinding(unittest.TestCase):
    def test_prepare_rejects_config_not_matching_draw(self):
        with fixture(harness_ids=('bare',)) as (folder, config, calls):
            config['harnesses'] = [{'id': 'not_in_panel', 'source': BARE_SOURCE}]
            with self.assertRaises(ValueError):
                prepare(config)

    def test_prepare_binds_draw_hashes(self):
        with fixture(harness_ids=('bare',)) as (folder, config, calls):
            manifest, _tasks = prepare(config)
            self.assertEqual(manifest['panel_draw']['panel'], ['bare'])
            self.assertIn('panel_draw_sha256', manifest['panel_draw'])
            self.assertEqual(manifest['panel_draw']['panel'], ['bare'])


class TestWorkerCell(unittest.TestCase):
    def test_worker_runs_bare_cell_with_accounting(self):
        with fixture(harness_ids=('bare',)) as (folder, config, calls):
            manifest, tasks = prepare(config)
            cell = {'repeat': 1, 'harness': 'bare', 'task': tasks[0]['id']}
            wdir = folder / 'worker1'
            wdir.mkdir()
            request = {'manifest': manifest, 'cell': cell, 'task': tasks[0],
                       'harness': manifest['harnesses'][0], 'folder': str(wdir),
                       'dataset_root': config['dataset_root'],
                       'global_budget_path': str(folder / 'gb.json')}
            (wdir / 'request.json').write_text(json.dumps(request), encoding='utf-8')
            gate = wdir / 'gate'
            gate.write_text('assigned', encoding='utf-8')
            worker(request, gate)
            ledger = read_ledger(wdir)
            result = ledger['tasks'][0]['result']
            self.assertEqual(result['official_correct'], 1)
            self.assertEqual(result['n_llm_calls'], 1)
            self.assertEqual(result['accounting']['logical_calls'], 1)
            self.assertEqual(result['accounting']['known_total_tokens'], 15)
            self.assertEqual(result['accounting']['responses_missing_usage'], 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]['body']['model'], 'GLM-5.3-Flash')

    def test_prepare_rejects_source_outside_agents_dir(self):
        with fixture(harness_ids=('bare',)) as (folder, config, calls):
            config['harnesses'] = [{'id': 'bare', 'source': 'experiment/revision/windows_job.py'}]
            (folder / 'draw2.json').write_text(json.dumps(
                {'salt': 's', 'panel': ['bare'], 'eligible': ['bare']}), encoding='utf-8')
            config['panel_draw_path'] = str(folder / 'draw2.json')
            with self.assertRaises(ValueError):
                prepare(config)


class TestGlobalBudget(unittest.TestCase):
    def test_budget_reserves_and_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'gb.json'
            budget = GlobalBudget(path, 3)
            self.assertEqual(budget.reserve(2), 2)
            self.assertEqual(budget.reserve(1), 3)
            with self.assertRaises(RuntimeError):
                budget.reserve(1)

    def test_budget_state_survives_reopen(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'gb.json'
            GlobalBudget(path, 5).reserve(2)
            self.assertEqual(GlobalBudget(path, 5).spent(), 2)

    def test_budget_ceiling_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'gb.json'
            GlobalBudget(path, 5)
            with self.assertRaises(ValueError):
                GlobalBudget(path, 6)


class TestCollect(unittest.TestCase):
    def test_collect_runs_cells_and_seals(self):
        with fixture(harness_ids=('bare', 'clone-c1'), repeats=(1,),
                     concurrency=2) as (folder, config, calls):
            result = collect(config)
            finished = [t for t in result['tasks'] if t['result'] is not None]
            self.assertEqual(len(finished), 200)  # 100 dev tasks x 2 members x 1 repeat
            self.assertEqual(len(calls), 200)
            for task in finished:
                self.assertEqual(task['result']['official_correct'], 1)
            self.assertEqual(result['manifest']['shard'], {'index': 0, 'count': 1})

    def test_collect_exhausts_global_budget_and_snapshots(self):
        with fixture(harness_ids=('bare',), repeats=(1,), max_attempts=5) as (folder, config, calls):
            with self.assertRaises(RuntimeError) as caught:
                collect(config)
            self.assertIn('ceiling', str(caught.exception))
            snapshot = json.loads((folder / 'acq' / 'snapshot.json').read_text(encoding='utf-8'))
            self.assertTrue(any(e['kind'] == 'acquisition_stopped' for e in snapshot['events']))

    def test_collect_refuses_to_seal_on_overall_failure(self):
        with fixture(harness_ids=('bare',), repeats=(1,), fail_status=500) as (folder, config, calls):
            with self.assertRaises(RuntimeError) as caught:
                collect(config)  # 500 with no retry: closed requests, all fail
            self.assertIn('failure rate', str(caught.exception))
            snapshot = json.loads((folder / 'acq' / 'snapshot.json').read_text(encoding='utf-8'))
            done = [t for t in snapshot['tasks'] if t['result'] is not None]
            self.assertTrue(all(t['result'].get('official_correct') is None for t in done))
            self.assertEqual(len(done), 100)

    def test_shard_partition_is_disjoint_and_complete(self):
        with fixture(harness_ids=('bare',), repeats=(1,), concurrency=2) as (folder, config, calls):
            config['shard_index'], config['shards'] = 0, 2
            a = collect(dict(config, output=config['output'] + '_a'))
            config2 = dict(config, shard_index=1, shards=2,
                           output=config['output'] + '_b',
                           acquisition_id='math-fresh-test-loopback-b')
            b = collect(config2)

            def cells(result):
                return {(t['result']['repeat'], t['result']['harness'], t['result']['task'])
                        for t in result['tasks'] if t['result'] is not None
                        and t['result'].get('official_correct') == 1}
            ca, cb = cells(a), cells(b)
            self.assertEqual(len(ca), 50)
            self.assertEqual(len(cb), 50)
            self.assertEqual(ca & cb, set())

    def test_real_panel_draw_matches_frozen_file(self):
        draw = json.loads(Path('review-stage/WP1R_PANEL_DRAW.json').read_text(encoding='utf-8'))
        expected = sorted(['gsm_deepseek_s0_g3', 'gsm_ernie_s0_g3', 'gsm_glm_s0_g6',
                           'gsm_kimi_s0_g3', 'gsm_kimi_s0_g4', 'gsm_minimax_s0_g0',
                           'gsm_minimax_s0_g3', 'gsm_qwen_s0_g5', 'bare'])
        self.assertEqual(sorted(e[0] if isinstance(e, list) else e for e in draw['panel']), expected)
        self.assertEqual(draw['salt'], 'wp1r-panel-v1-20260915')


if __name__ == '__main__':
    unittest.main()
