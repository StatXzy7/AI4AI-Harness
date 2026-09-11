"""One trusted SQL task per Windows Job Object, with durable per-task HTTP ledgers.

Answers are frozen when solve returns; racing calls may drain afterward. Unknown
cost/completion stops the acquisition without discarding the returned answer.
No production run is implied by this development entry point.
"""
import argparse
from contextlib import closing
from dataclasses import asdict
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from experiment.revision.fresh_collect import ROOT, TTHE, fetch_readonly, file_hash, validate_inputs
from experiment.revision.fresh_runtime import FreshSolver, RunStore, SolverSettings, digest
from experiment.revision.windows_job import SuspendedWorker, WindowsJob


def require_launch_identity(record):
    """Reject draft identities before preparing inputs or entering a worker."""
    identity = record.get('acquisition_id')
    if not isinstance(identity, str) or not identity.strip() or 'draft' in identity.casefold():
        raise ValueError('DRAFT or empty acquisition identity cannot launch; offline prepare only')


def prepare(config):
    settings = SolverSettings(**config['solver'])
    for field in ('worker_wall_seconds', 'drain_seconds'):
        if not math.isfinite(config[field]) or config[field] <= 0:
            raise ValueError('Worker wall and drain intervals must be finite and positive')
    if config['worker_wall_seconds'] <= config['drain_seconds']:
        raise ValueError('Worker wall must exceed its drain interval')
    if config.get('cache_mode') != 'off' or not config['acquisition_id']:
        raise ValueError('Explicit acquisition identity and cache_mode=off required')
    if not os.environ.get(config['api_key_env']):
        raise ValueError('Provider key is absent')
    repeats = config['repeats']
    if not repeats or any(type(r) is not int or r < 0 for r in repeats) or len(set(repeats)) != len(repeats):
        raise ValueError('Expected distinct nonnegative repeats')
    harnesses = [dict(h) for h in config['harnesses']]
    if not harnesses or len({h['id'] for h in harnesses}) != len(harnesses):
        raise ValueError('Expected distinct harness identities')
    for h in harnesses:
        source = (ROOT / h['source']).resolve()
        if not h['id'] or not source.is_relative_to(TTHE / 'text_to_sql/agents') or not source.is_file():
            raise ValueError('Expected a trusted local harness source')
        h['source'] = source.relative_to(ROOT).as_posix()
    sys.path.insert(0, str(TTHE))
    from ase.dataset import BirdDataset
    os.environ.pop('BIRD_DEV_FILE', None)
    dataset = BirdDataset(str(Path(config['dataset_root']).resolve()))
    split = json.loads(Path(config['split_path']).read_text(encoding='utf-8'))['by_db']
    tasks, db_hashes = [], {}
    for db_id, indices in split.items():
        questions = dataset.eval_questions(db_id)
        db = dataset.get_database(db_id)
        db_hashes[db.sqlite_path] = file_hash(db.sqlite_path)
        for index in indices:
            if type(index) is not int or not 0 <= index < len(questions):
                raise ValueError('Task index outside dataset')
            q = questions[index]
            if fetch_readonly(db.sqlite_path, q.gold_sql) is None:
                raise ValueError('Gold query failed before acquisition')
            tasks.append({'id': f'{db_id}#{index}', 'db_id': db_id, 'question': q.question,
                          'gold_sql': q.gold_sql, 'database_path': db.sqlite_path})
    if not tasks or len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('Expected distinct nonempty tasks')
    sources = sorted(set(list((TTHE / 'ase').rglob('*.py')) + list((TTHE / 'text_to_sql').rglob('*.py')) +
                         [ROOT / f'experiment/revision/{name}.py' for name in
                          ('fresh_runtime', 'fresh_collect', 'windows_job', 'isolated_collect')]))
    hashes = {str(path): file_hash(path) for path in sources}
    manifest = {'version': 'isolated-acquisition-v2-development', 'acquisition_id': config['acquisition_id'],
                'missing_usage_policy': 'stop-before-next-cell-preserve-pending-v1',
                'cache_mode': 'off', 'solver': asdict(settings), 'api_key_env': config['api_key_env'],
                'worker_wall_seconds': config['worker_wall_seconds'], 'drain_seconds': config['drain_seconds'],
                'task_order': 'repeat-harness-task', 'harnesses': harnesses, 'repeats': repeats,
                'tasks_sha256': digest(tasks), 'split_sha256': file_hash(config['split_path']),
                'protocol_sha256': file_hash(config['protocol_path']), 'database_sha256': db_hashes,
                'source_sha256': hashes, 'judge': 'raw-set-readonly-30s-v1', 'python': sys.version,
                'packages': dict(sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions()))}
    return manifest, tasks


def read_ledger(folder):
    path = Path(folder) / 'ledger.sqlite'
    if not path.exists():
        return None
    # Caller has verified the whole Job is empty. A killed writer can leave a
    # hot rollback journal; mode=rw permits recovery but never creates a database.
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)) as conn:
        return {'tasks': [{'key': k, 'result': json.loads(v) if v is not None else None}
                          for k, v in conn.execute('SELECT key,result FROM tasks ORDER BY key')],
                'events': [{'id': i, **json.loads(v)} for i, v in conn.execute('SELECT id,value FROM events ORDER BY id')]}


def run_worker(request_path, folder, wall_seconds):
    """Assign before opening the gate; always settle local process lifetime before returning."""
    folder = Path(folder)
    gate = folder / ('start-' + uuid.uuid4().hex)
    command = [sys.executable, '-m', 'experiment.revision.isolated_collect', '--worker', str(request_path),
               '--gate', str(gate)]
    with (folder / 'stdout.txt').open('wb') as stdout, (folder / 'stderr.txt').open('wb') as stderr, WindowsJob() as job:
        process = SuspendedWorker(command, ROOT, stdout, stderr)
        started = time.monotonic()
        reason = 'exited'
        try:
            job.assign(process)
            gate.write_text('assigned', encoding='utf-8')
            process.resume()
            try:
                process.wait(timeout=wall_seconds)
            except subprocess.TimeoutExpired:
                reason = 'wall_timeout'
                job.terminate()
                process.wait(timeout=5)
            before = job.accounting()
            if before['active_processes']:
                try:
                    # Windows launcher/exit accounting can lag the root handle.
                    job.wait_empty(seconds=1)
                except RuntimeError:
                    reason = 'descendants_survived' if reason == 'exited' else reason
                    job.terminate()
            after = job.wait_empty()
            return {'pid': process.pid, 'exit_code': process.returncode, 'reason': reason,
                    'wall_seconds': time.monotonic() - started, 'before_cleanup': before, 'after_cleanup': after}
        finally:
            # Assign failure occurs while the worker is still at its gate.
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            # CloseHandle alone is only a last-resort kill; verify the tree here.
            if job.accounting()['active_processes']:
                job.terminate()
                job.wait_empty()
            process.close()


def worker(request, gate):
    require_launch_identity(request['manifest'])
    deadline = time.monotonic() + 30
    while not Path(gate).exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('Worker was never assigned to its process job')
        time.sleep(0.01)
    manifest, task, harness = request['manifest'], request['task'], request['harness']
    api_key = os.environ.get(manifest['api_key_env'])
    if not api_key:
        raise ValueError('Provider key is absent')
    for key in list(os.environ):
        if key.startswith(('SOLVER_', 'SQL_SOLVER_', 'BIRD_', 'ASE_')):
            del os.environ[key]
    folder = Path(request['folder'])
    cell = request['cell']
    # If os._exit is required, bootstrap files stay with this worker's evidence,
    # rather than becoming detached directories in the system temp folder.
    with RunStore(folder, {**manifest, 'cell': cell}) as store, tempfile.TemporaryDirectory(prefix='bridge_', dir=folder) as temp:
        bootstrap = Path(temp) / 'config.json'
        bootstrap.write_text(json.dumps({'llm': {'provider': 'mock'},
                                         'dataset': {'name': 'bird', 'bird_root': request['dataset_root']},
                                         'output_dir': temp}), encoding='utf-8')
        os.environ['TTHE_CONFIG'] = str(bootstrap)
        os.environ['SQL_SOLVER_CACHE'] = str(Path(temp) / 'unused.json')
        sys.path.insert(0, str(TTHE))
        from text_to_sql import bridge
        from text_to_sql.harness_base import SQLHarness
        task_key, needed = store.begin(cell)
        if not needed:
            raise RuntimeError('Worker output must be fresh; parent alone handles resume')
        solver = FreshSolver(store, SolverSettings(**manifest['solver']), api_key)
        def frozen(prompt, system='', temperature=0., n=1, seq=0):
            override = getattr(bridge._tls, 'temp_override', None)
            return solver(prompt, system, override if override is not None else temperature, n, seq)
        bridge.solver_llm = frozen
        base_threads = set(threading.enumerate())
        try:
            with solver.bind(task_key):
                name = 'text_to_sql.agents._isolated_' + digest(harness)
                spec = importlib.util.spec_from_file_location(name, ROOT / harness['source'])
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                classes = [v for v in vars(module).values() if isinstance(v, type) and v is not SQLHarness
                           and issubclass(v, SQLHarness) and v.__module__ == name]
                if len(classes) != 1:
                    raise ValueError('Expected exactly one harness class')
                instance = classes[0](bridge.get_db(task['db_id']))
                started = time.monotonic()
                sql = instance.solve(task['question'])
                answer_seconds = time.monotonic() - started
                if not isinstance(sql, str):
                    raise TypeError('Harness returned non-string SQL')
                store.event('answer_returned', task=task_key, final_sql=sql, answer_seconds=answer_seconds)
                # Preserve the original answer, while allowing racing workers to finish
                # and charge their requests to this same immutable task.
                drain_deadline = time.monotonic() + manifest['drain_seconds']
                while set(threading.enumerate()) - base_threads:
                    if time.monotonic() >= drain_deadline:
                        store.event('drain_expired', task=task_key, local_threads='pending',
                                     provider_completion='unknown')
                        # No destructor or executor shutdown may extend the declared drain.
                        os._exit(3)
                    time.sleep(0.01)
            prediction = fetch_readonly(task['database_path'], sql)
            gold = fetch_readonly(task['database_path'], task['gold_sql'])
            if gold is None:
                raise RuntimeError('Gold became unexecutable')
            if file_hash(ROOT / harness['source']) != manifest['source_sha256'][str(ROOT / harness['source'])]:
                store.event('run_invalid', task=task_key, reason='harness_source_changed')
                raise RuntimeError('Harness source changed')
            store.finish(task_key, {**cell, 'final_sql': sql, 'answer_seconds': answer_seconds,
                                    'official_correct': int(prediction is not None and set(prediction) == set(gold)),
                                    'trace': instance._trace})
        except Exception as exc:
            store.event('task_error', task=task_key, error_type=type(exc).__name__)
            raise
        finally:
            solver.close()


def import_events(store, parent_key, child):
    """Re-key durable event references while keeping the worker event IDs for audit."""
    remap = {}
    for original in child['events']:
        value = dict(original)
        child_id = value.pop('id')
        kind = value.pop('kind')
        value['worker_task'] = value.pop('task', None)
        value['task'] = parent_key
        value['worker_event'] = child_id
        for field in ('logical', 'attempt'):
            if field in value:
                value[field] = remap[value[field]]
        remap[child_id] = store.event(kind, **value)


def collect(config):
    require_launch_identity(config)
    manifest, tasks = prepare(config)
    output = Path(config['output']).resolve()
    with RunStore(output, manifest) as store:
        for repeat in manifest['repeats']:
            for harness in manifest['harnesses']:
                for task in tasks:
                    cell = {'repeat': repeat, 'harness': harness['id'], 'task': task['id']}
                    key, needed = store.begin(cell)
                    if not needed:
                        continue
                    folder = output / 'workers' / key
                    folder.mkdir(parents=True, exist_ok=False)
                    request = {'manifest': manifest, 'cell': cell, 'task': task, 'harness': harness,
                               'folder': str(folder), 'dataset_root': str(Path(config['dataset_root']).resolve())}
                    request_path = folder / 'request.json'
                    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
                    process = run_worker(request_path, folder, manifest['worker_wall_seconds'])
                    store.event('worker_exited', task=key, **process)
                    try:
                        child = read_ledger(folder)
                    except sqlite3.DatabaseError as exc:
                        store.event('ledger_read_error', task=key, error_type=type(exc).__name__,
                                    request_accounting='unknown')
                        child = None
                    if child:
                        import_events(store, key, child)
                    success = (process['reason'] == 'exited' and process['exit_code'] == 0 and child and
                               len(child['tasks']) == 1 and child['tasks'][0]['result'] is not None)
                    if not success:
                        store.event('acquisition_stopped', task=key, reason='worker_or_requests_unresolved')
                        (output / 'snapshot.json').write_text(json.dumps(store.snapshot(), indent=2, ensure_ascii=False),
                                                               encoding='utf-8')
                        raise RuntimeError('Worker stopped; preserve answer and unknown requests, do not retry automatically')
                    child_result = child['tasks'][0]['result']
                    accounting = child_result.get('accounting', {})
                    if accounting.get('responses_missing_usage') != 0 or accounting.get('total_tokens') is None:
                        store.event('acquisition_stopped', task=key, reason='response_usage_unknown',
                                    answer_preserved=True, worker_result=child_result)
                        (output / 'snapshot.json').write_text(json.dumps(store.snapshot(), indent=2, ensure_ascii=False),
                                                               encoding='utf-8')
                        raise RuntimeError('Response usage unknown; preserve answer and pending cell, do not retry automatically')
                    store.finish(key, {**child_result, 'worker_pid': process['pid']})
        validate_inputs(store, {**manifest['source_sha256'], **manifest['database_sha256']})
        store.event('run_verified', cells=len(tasks) * len(manifest['harnesses']) * len(manifest['repeats']))
        result = store.snapshot()
        (output / 'snapshot.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--gate', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker.read_text(encoding='utf-8')), args.gate)
    else:
        result = collect(json.loads(args.config.read_text(encoding='utf-8')))
        print(f"Verified {len(result['tasks'])} isolated cells")


if __name__ == '__main__':
    main()
