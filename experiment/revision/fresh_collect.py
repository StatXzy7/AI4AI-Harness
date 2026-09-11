"""Serial, versioned fresh acquisition for frozen trusted SQL harnesses.

Run only with a reviewed acquisition config and authorized provider budget.
Historical collector/runtime sources are retained. This is a new execution
version, not a transparent replacement for historical measurements.
"""
import argparse
from contextlib import closing
from dataclasses import asdict
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time

from experiment.revision.fresh_runtime import FreshSolver, RunStore, SolverSettings, digest

ROOT = Path(__file__).resolve().parents[2]
TTHE = ROOT / 'external/TTHE'


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_inputs(store, hashes):
    if any(not Path(path).is_file() or file_hash(path) != value for path, value in hashes.items()):
        store.event('run_invalid', reason='source_or_database_changed_during_acquisition')
        raise RuntimeError('Source/database changed during acquisition; results are invalid')


def fetch_readonly(path, sql):
    """Raw tuple/set scoring with the project's 30s limit, on a read-only connection."""
    if not (sql or '').strip():
        return None
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            conn.text_factory = lambda b: b.decode('utf-8', 'ignore')
            conn.execute('PRAGMA query_only=ON')
            deadline = time.monotonic() + 30
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return None


def collect(config):
    if 'text_to_sql.bridge' in sys.modules:
        raise RuntimeError('Use a fresh interpreter for each collector invocation')
    settings = SolverSettings(**config['solver'])
    api_key = os.environ.get(config['api_key_env'])
    if not api_key:
        raise ValueError('Configured provider key is absent')
    if not config['acquisition_id'] or config.get('cache_mode') != 'off':
        raise ValueError('New acquisitions require an explicit identity and cache_mode=off')
    repeats = config['repeats']
    if not repeats or any(type(r) is not int or r < 0 for r in repeats) or len(set(repeats)) != len(repeats):
        raise ValueError('Repeats must be distinct nonnegative integers')
    harnesses = [dict(h) for h in config['harnesses']]
    if not harnesses or len({h['id'] for h in harnesses}) != len(harnesses):
        raise ValueError('Harness identities must be nonempty and distinct')
    sources = []
    for harness in harnesses:
        source = (ROOT / harness['source']).resolve()
        if not harness['id'] or not source.is_relative_to(TTHE / 'text_to_sql/agents') or not source.is_file():
            raise ValueError('Expected a named trusted local harness source')
        harness['source'] = source.relative_to(ROOT).as_posix()
        sources.append(source)
    dataset_root = Path(config['dataset_root']).resolve()
    split_path = Path(config['split_path']).resolve()
    split = json.loads(split_path.read_text(encoding='utf-8'))['by_db']
    sys.path.insert(0, str(TTHE))
    from ase.dataset import BirdDataset
    for key in list(os.environ):
        if key.startswith(('SOLVER_', 'SQL_SOLVER_', 'BIRD_', 'ASE_')):
            del os.environ[key]
    dataset = BirdDataset(str(dataset_root))
    tasks = []
    databases = {}
    for db_id, indices in split.items():
        questions = dataset.eval_questions(db_id)
        database = dataset.get_database(db_id)
        databases[db_id] = database
        for index in indices:
            if type(index) is not int or index < 0 or index >= len(questions):
                raise ValueError('Task index outside dataset')
            q = questions[index]
            tasks.append({'id': f'{db_id}#{index}', 'db_id': db_id,
                          'question': q.question, 'gold_sql': q.gold_sql})
    if not tasks or len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('Task list must be nonempty and unique')
    measured = sorted(set(sources + list((TTHE / 'ase').rglob('*.py')) +
                          list((TTHE / 'text_to_sql').rglob('*.py')) +
                          [ROOT / 'experiment/revision/fresh_runtime.py', Path(__file__).resolve()]))
    source_hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): file_hash(p) for p in measured}
    manifest = {'version': 'fresh-acquisition-v1-development',
                'acquisition_id': config['acquisition_id'], 'cache_mode': 'off',
                'solver': asdict(settings), 'api_key_env': config['api_key_env'],
                'harnesses': harnesses, 'repeats': repeats, 'tasks_sha256': digest(tasks),
                'split_sha256': file_hash(split_path), 'source_sha256': source_hashes,
                'protocol_sha256': file_hash(config['protocol_path']),
                'data_sha256': {db: file_hash(value.sqlite_path) for db, value in databases.items()},
                'judge': 'raw-set-readonly-30s-v1', 'python': sys.version,
                'packages': dict(sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions()))}
    output = Path(config['output']).resolve()
    with RunStore(output, manifest) as store, tempfile.TemporaryDirectory(prefix='fresh_bridge_') as temporary:
        bootstrap = Path(temporary) / 'config.json'
        bootstrap.write_text(json.dumps({'llm': {'provider': 'mock'},
                                         'dataset': {'name': 'bird', 'bird_root': str(dataset_root)},
                                         'output_dir': temporary}), encoding='utf-8')
        os.environ['TTHE_CONFIG'] = str(bootstrap)
        os.environ['SQL_SOLVER_CACHE'] = str(Path(temporary) / 'unused_cache.json')
        from text_to_sql import bridge
        from text_to_sql.harness_base import SQLHarness
        classes = {}
        startup_threads = set(threading.enumerate())
        try:
            for harness, source in zip(harnesses, sources):
                name = 'text_to_sql.agents._fresh_' + digest(harness)
                spec = importlib.util.spec_from_file_location(name, source)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                found = [c for c in vars(module).values() if isinstance(c, type) and c is not SQLHarness
                         and issubclass(c, SQLHarness) and c.__module__ == name]
                if len(found) != 1:
                    raise ValueError('Harness must define exactly one SQLHarness class')
                classes[harness['id']] = found[0]
            if set(threading.enumerate()) - startup_threads:
                store.event('run_invalid', reason='harness_started_background_thread_on_import')
                raise RuntimeError('Harness import left background threads running')
            gold = {t['id']: fetch_readonly(databases[t['db_id']].sqlite_path, t['gold_sql']) for t in tasks}
            if any(v is None for v in gold.values()):
                raise ValueError('Gold query failed before acquisition')
            # Frozen explicit order. This is recorded, not claimed randomized.
            for repeat in repeats:
                for harness in harnesses:
                    for task in tasks:
                        cell = {'repeat': repeat, 'harness': harness['id'], 'task': task['id']}
                        task_key, needs_work = store.begin(cell)
                        if not needs_work:
                            continue
                        solver = FreshSolver(store, settings, api_key)
                        def frozen_solver(prompt, system='', temperature=0.0, n=1, seq=0, _solver=solver):
                            override = getattr(bridge._tls, 'temp_override', None)
                            return _solver(prompt, system, override if override is not None else temperature, n, seq)
                        bridge.solver_llm = frozen_solver
                        task_threads = set(threading.enumerate())
                        try:
                            with solver.bind(task_key):
                                instance = classes[harness['id']](databases[task['db_id']])
                                sql = instance.solve(task['question'])
                                if set(threading.enumerate()) - task_threads:
                                    store.event('run_invalid', task=task_key, reason='harness_left_background_threads')
                                    raise RuntimeError('Harness left unjoined threads; stop before the next task')
                            if not isinstance(sql, str):
                                raise TypeError('Harness returned non-string SQL')
                            prediction = fetch_readonly(instance.db.sqlite_path, sql)
                            # A source change cannot silently produce accepted rows under the old identity.
                            if file_hash(ROOT / harness['source']) != source_hashes[harness['source']]:
                                raise RuntimeError('Runtime source changed during acquisition')
                            store.finish(task_key, {**cell, 'final_sql': sql,
                                                    'official_correct': int(prediction is not None and
                                                                            set(prediction) == set(gold[task['id']])),
                                                    'trace': instance._trace})
                        except Exception as exc:
                            store.event('task_error', task=task_key, error_type=type(exc).__name__)
                            raise
                        finally:
                            solver.close()
            validate_inputs(store, {**{databases[db].sqlite_path: value for db, value in manifest['data_sha256'].items()},
                                    **{ROOT / p: value for p, value in source_hashes.items()}})
            store.event('run_verified', tasks=len(tasks) * len(harnesses) * len(repeats))
            snapshot = store.snapshot()
            (output / 'snapshot.json').write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n',
                                                   encoding='utf-8')
            return snapshot
        finally:
            # The process must not dispatch another task through the last bound solver.
            bridge.solver_llm = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    result = collect(json.loads(args.config.read_text(encoding='utf-8')))
    print(f"Completed {len(result['tasks'])} cells; ledger remains the authoritative record")


if __name__ == '__main__':
    main()
