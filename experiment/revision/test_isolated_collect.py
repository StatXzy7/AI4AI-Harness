"""Real Windows process/job and loopback tests; never calls a paid provider."""
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

from experiment.revision.fresh_collect import ROOT
from experiment.revision.fresh_runtime import SolverSettings
from experiment.revision.isolated_collect import read_ledger, worker
from experiment.revision.windows_job import SuspendedWorker, WindowsJob


@contextmanager
def provider(delay_duplicate=False, missing_usage=False):
    calls = []
    lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            prompt = request['messages'][-1]['content']
            with lock:
                delay = delay_duplicate and any(c['prompt'] == prompt for c in calls)
                calls.append({'prompt': prompt, 'request': request})
                index = len(calls)
            if delay:
                time.sleep(1.2)
            payload = {'id': f'response-{index}', 'object': 'chat.completion', 'created': 1,
                       'model': request['model'], 'usage': {'prompt_tokens': 3, 'completion_tokens': 2,
                                                          'total_tokens': 5},
                       'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
                           'role': 'assistant', 'content': f'SELECT count(*) FROM ledger -- response {index}'}}]}
            if missing_usage:
                payload.pop('usage')
            raw = json.dumps(payload).encode('utf-8')
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Expected only when testing termination with remote work pending.
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
def fixture(url, drain=3, wall=15, harness='cand_bird_g1_b0r1_g1', repeats=(0, 1)):
    with tempfile.TemporaryDirectory(prefix='isolated_test_') as temporary:
        folder = Path(temporary)
        db_dir = folder / 'dev_databases/fixture'
        db_dir.mkdir(parents=True)
        conn = sqlite3.connect(db_dir / 'fixture.sqlite')
        conn.execute('CREATE TABLE ledger (id INTEGER)')
        conn.executemany('INSERT INTO ledger VALUES (?)', [(1,), (2,)])
        conn.commit()
        conn.close()
        (folder / 'dev.json').write_text(json.dumps([{'db_id': 'fixture', 'question': 'How many entries?',
                                                     'SQL': 'SELECT count(*) FROM ledger'}]), encoding='utf-8')
        (folder / 'split.json').write_text(json.dumps({'by_db': {'fixture': [0]}}), encoding='utf-8')
        (folder / 'protocol.txt').write_text('Synthetic isolation fixture, not a scientific freeze.', encoding='utf-8')
        config = {'acquisition_id': 'isolated-fixture', 'cache_mode': 'off',
                  'solver': asdict(SolverSettings(url, 'fixture', timeout_seconds=20)),
                  'api_key_env': 'ISOLATED_FIXTURE_KEY', 'dataset_root': str(folder),
                  'split_path': str(folder / 'split.json'), 'protocol_path': str(folder / 'protocol.txt'),
                  'repeats': list(repeats), 'harnesses': [{'id': harness,
                      'source': f'external/TTHE/text_to_sql/agents/{harness}.py'}],
                  'worker_wall_seconds': wall, 'drain_seconds': drain, 'output': str(folder / 'output')}
        path = folder / 'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        yield folder, path


def invoke(path):
    return subprocess.run([sys.executable, '-m', 'experiment.revision.isolated_collect', '--config', str(path)],
                          cwd=ROOT, env={**os.environ, 'ISOLATED_FIXTURE_KEY': 'dummy-local'},
                          capture_output=True, text=True, encoding='utf-8', timeout=40)


@contextmanager
def stalled_provider():
    received = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            received.append(time.monotonic())
            time.sleep(8)
            # The local process may be dead while a remote service still runs.
            try:
                self.send_response(500)
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class IsolatedCollectTests(unittest.TestCase):
    def test_draft_cli_never_prepares_or_calls_provider(self):
        with provider() as (url, calls), fixture(url) as (folder, path):
            config = json.loads(path.read_text(encoding='utf-8'))
            config['acquisition_id'] = 'provider-pilot-dRaFt'
            # Even invalid input paths must remain untouched by the draft launch.
            config['dataset_root'] = str(folder / 'absent')
            path.write_text(json.dumps(config), encoding='utf-8')
            result = invoke(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('DRAFT or empty acquisition identity cannot launch', result.stderr)
            self.assertEqual(calls, [])
            self.assertFalse((folder / 'output').exists())

    def test_direct_worker_rejects_draft_before_gate_or_credentials(self):
        with self.assertRaisesRegex(ValueError, 'DRAFT'):
            worker({'manifest': {'acquisition_id': 'pilot-DRAFT'}}, None)

    def test_missing_usage_preserves_answer_and_stops_before_next_cell_and_resume(self):
        with provider(missing_usage=True) as (url, calls), fixture(url, harness='bare') as (folder, path):
            result = invoke(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Response usage unknown', result.stderr)
            snapshot = json.loads((folder / 'output/snapshot.json').read_text(encoding='utf-8'))
            self.assertEqual(snapshot['manifest']['version'], 'isolated-acquisition-v2-development')
            self.assertEqual(snapshot['manifest']['missing_usage_policy'],
                             'stop-before-next-cell-preserve-pending-v1')
            self.assertEqual(len(snapshot['tasks']), 1)
            self.assertIsNone(snapshot['tasks'][0]['result'])
            stopped = next(e for e in snapshot['events'] if e['kind'] == 'acquisition_stopped')
            self.assertEqual(stopped['reason'], 'response_usage_unknown')
            self.assertEqual(stopped['worker_result']['official_correct'], 1)
            self.assertTrue(stopped['worker_result']['final_sql'])
            self.assertEqual(stopped['worker_result']['accounting']['responses_missing_usage'], 1)
            self.assertIsNone(stopped['worker_result']['accounting']['total_tokens'])
            self.assertEqual(next(e for e in snapshot['events'] if e['kind'] == 'worker_exited')
                             ['after_cleanup']['active_processes'], 0)
            self.assertFalse(any(e['kind'] == 'run_verified' for e in snapshot['events']))
            self.assertEqual(len(calls), 1)
            again = invoke(path)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn('Unfinished', again.stderr)
            self.assertEqual(len(calls), 1)

    def test_hot_rollback_journal_recovers_committed_request_evidence(self):
        with tempfile.TemporaryDirectory(prefix='journal_test_') as folder:
            path = Path(folder) / 'ledger.sqlite'
            conn = sqlite3.connect(path)
            conn.execute('CREATE TABLE tasks (key TEXT,result TEXT)')
            conn.execute('CREATE TABLE events (id INTEGER PRIMARY KEY,value TEXT)')
            conn.execute('INSERT INTO tasks VALUES (?,NULL)', ('pending',))
            original = json.dumps({'kind': 'http_start', 'task': 'pending', 'padding': 'a' * 2048})
            conn.executemany('INSERT INTO events(value) VALUES (?)', [(original,)] * 200)
            conn.commit()
            conn.close()
            code = (f'import sqlite3,os; c=sqlite3.connect({str(path)!r}); '
                    'c.execute("PRAGMA cache_size=5"); c.execute("BEGIN IMMEDIATE"); '
                    'c.execute("UPDATE events SET value=?",("b"*2048,)); os._exit(3)')
            result = subprocess.run([sys.executable, '-c', code], creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 3)
            self.assertTrue(path.with_name('ledger.sqlite-journal').exists())
            recovered = read_ledger(folder)
            self.assertEqual(len(recovered['events']), 200)
            self.assertTrue(all(e['kind'] == 'http_start' for e in recovered['events']))
            self.assertIsNone(recovered['tasks'][0]['result'])

    def test_suspended_assignment_contains_and_terminates_descendants(self):
        with tempfile.TemporaryDirectory(prefix='job_test_') as folder:
            marker = Path(folder) / 'child.txt'
            code = ('import subprocess,sys,time; from pathlib import Path; '
                    'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); '
                    f'Path({str(marker)!r}).write_text(str(p.pid));time.sleep(30)')
            with open(os.devnull, 'wb') as output, WindowsJob() as job:
                process = SuspendedWorker([sys.executable, '-c', code], ROOT, output, output)
                try:
                    job.assign(process)
                    self.assertFalse(marker.exists())
                    process.resume()
                    deadline = time.monotonic() + 5
                    while not marker.exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(marker.exists())
                    self.assertGreaterEqual(job.accounting()['active_processes'], 2)
                    job.terminate()
                    self.assertEqual(job.wait_empty()['active_processes'], 0)
                    self.assertIsNotNone(process.wait(timeout=5))
                finally:
                    if process.poll() is None:
                        job.terminate()
                        process.wait(timeout=5)
                    job.wait_empty()
                    process.close()

    def test_real_race_drains_and_repeats_in_distinct_processes(self):
        with provider(delay_duplicate=True) as (url, calls), fixture(url) as (folder, path):
            run = invoke(path)
            self.assertEqual(run.returncode, 0, run.stderr)
            snapshot = json.loads((folder / 'output/snapshot.json').read_text(encoding='utf-8'))
            self.assertEqual(len(calls), 4)
            tasks = snapshot['tasks']
            self.assertEqual(len(tasks), 2)
            self.assertEqual(len({t['result']['worker_pid'] for t in tasks}), 2)
            self.assertTrue(all(t['result']['official_correct'] == 1 for t in tasks))
            self.assertTrue(all(t['result']['accounting']['http_attempts'] == 2 for t in tasks))
            self.assertTrue(all(t['result']['accounting']['total_tokens'] == 10 for t in tasks))
            exits = [e for e in snapshot['events'] if e['kind'] == 'worker_exited']
            self.assertTrue(all(e['after_cleanup']['active_processes'] == 0 for e in exits))
            answer = next(e for e in snapshot['events'] if e['kind'] == 'answer_returned')
            late = [e for e in snapshot['events'] if e['kind'] == 'http_end' and e['task'] == answer['task']]
            self.assertTrue(any(e['time_ns'] > answer['time_ns'] for e in late))
            again = invoke(path)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(len(calls), 4)

    def test_drain_expiry_retains_answer_and_unmatched_requests_without_retry(self):
        with provider(delay_duplicate=True) as (url, calls), fixture(url, drain=0.05) as (folder, path):
            run = invoke(path)
            self.assertNotEqual(run.returncode, 0)
            snapshot = json.loads((folder / 'output/snapshot.json').read_text(encoding='utf-8'))
            self.assertEqual(len(snapshot['tasks']), 1)
            self.assertIsNone(snapshot['tasks'][0]['result'])
            events = snapshot['events']
            self.assertTrue(any(e['kind'] == 'answer_returned' and e['final_sql'] for e in events))
            self.assertTrue(any(e['kind'] == 'drain_expired' for e in events))
            self.assertEqual(sum(e['kind'] == 'http_start' for e in events), 2)
            self.assertEqual(sum(e['kind'] == 'http_end' for e in events), 1)
            self.assertEqual(next(e for e in events if e['kind'] == 'worker_exited')['after_cleanup']['active_processes'], 0)
            again = invoke(path)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn('Unfinished', again.stderr)
            self.assertEqual(len(calls), 2)

    def test_wall_timeout_kills_local_job_and_preserves_remote_unknown(self):
        with stalled_provider() as (url, received), fixture(url, drain=0.1, wall=4, harness='bare') as (folder, path):
            run = invoke(path)
            self.assertNotEqual(run.returncode, 0)
            snapshot = json.loads((folder / 'output/snapshot.json').read_text(encoding='utf-8'))
            self.assertIsNone(snapshot['tasks'][0]['result'])
            exit_event = next(e for e in snapshot['events'] if e['kind'] == 'worker_exited')
            self.assertEqual(exit_event['reason'], 'wall_timeout')
            self.assertEqual(exit_event['after_cleanup']['active_processes'], 0)
            self.assertEqual(len(received), 1)
            self.assertEqual(sum(e['kind'] == 'http_start' for e in snapshot['events']), 1)
            self.assertEqual(sum(e['kind'] == 'http_end' for e in snapshot['events']), 0)


if __name__ == '__main__':
    unittest.main()
