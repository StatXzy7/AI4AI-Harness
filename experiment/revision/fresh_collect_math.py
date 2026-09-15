"""Budgeted fresh acquisition for the frozen MATH-500 harness population.

MATH-side twin of isolated_collect.py: same RunStore / FreshSolver /
AuditedTransport / Windows-Job worker lifecycle, with the experiment/gsm8k
MathHarness interface (relative `from ..harness_base import MathHarness`) and
the archived numeric/latex judge from experiment/gsm8k/collect.py.

Protocol: review-stage/REAL_EVIDENCE_PROTOCOL_V1.md (frozen) plus its v1.x
amendments. Deviations from the SQL twin, all protocol-driven:

  * GlobalBudget — acquisition-wide atomic provider-attempt reservation shared
    by all shards and workers (file-locked state next to the ledger), so the
    45,000-attempt ceiling holds across concurrent workers and retries.
  * Clone members — every member (including clone slots) is loaded from its
    manifest source path under a unique module name inside gsm8k.agents, so
    identical bare source can carry distinct clone identities.
  * Concurrent parent — cells run under a bounded worker pool (2 -> 4);
    failures with fully closed requests are recorded and counted against the
    sliding stop window; unknown/budget-rejected requests stop acquisition.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import msvcrt
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experiment.revision.fresh_collect import file_hash, validate_inputs
from experiment.revision.fresh_runtime import (AuditedTransport, FreshSolver,
                                               ResourceBudget, RunStore,
                                               SolverSettings, digest)
from experiment.revision.interleaved_collect import schedule
from experiment.revision.isolated_collect import (import_events, read_ledger,
                                                  require_launch_identity)
from experiment.revision.windows_job import SuspendedWorker, WindowsJob

ROOT = Path(__file__).resolve().parents[2]
TTHE = ROOT / 'external/TTHE'
AGENTS = ROOT / 'experiment/gsm8k/agents'

MATH_SOURCES = [ROOT / 'experiment/gsm8k/harness_base.py',
                ROOT / 'experiment/gsm8k/collect.py',
                ROOT / 'experiment/gsm8k/__init__.py',
                ROOT / 'experiment/gsm8k/agents/__init__.py',
                ROOT / 'experiment/gsm8k/agents/bare.py',
                ROOT / 'artifacts/gsm8k_audit/math500_split.json',
                TTHE / 'text_to_sql/bridge.py',
                ROOT / 'experiment/revision/fresh_runtime.py',
                ROOT / 'experiment/revision/fresh_collect_math.py',
                ROOT / 'experiment/revision/isolated_collect.py',
                ROOT / 'experiment/revision/interleaved_collect.py',
                ROOT / 'experiment/revision/windows_job.py']


def lf_sha256(path: Path) -> str:
    """Hash with LF normalization; the archive's code_hash was written from
    in-memory LF text, while a Windows checkout materializes CRLF on disk."""
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


class GlobalBudget:
    """Acquisition-wide provider-attempt pool with atomic file-locked reserve.

    One instance per acquisition (state shared by every shard process and
    worker process). Attempts are never refunded: a sent request or an unknown
    outcome consumes its reservation (protocol §6: unknown is not zero-cost).
    """

    def __init__(self, path: Path, max_attempts: int):
        self.path = Path(path)
        self.max_attempts = int(max_attempts)
        if self.max_attempts < 1:
            raise ValueError('max_attempts must be positive')
        self._lock_path = self.path.with_suffix('.lock')
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({'max_attempts': self.max_attempts, 'reserved': 0})
        else:
            state = self._read()
            if state.get('max_attempts') != self.max_attempts:
                raise ValueError('Global budget ceiling differs from existing state')

    def _read(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def _write(self, state):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state), encoding='utf-8')
        os.replace(tmp, self.path)

    def reserve(self, n=1):
        with open(self._lock_path, 'a+b') as lock:
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                state = self._read()
                if state['max_attempts'] != self.max_attempts:
                    raise ValueError('Global budget ceiling changed under the reservation')
                reserved = state['reserved'] + n
                if reserved > self.max_attempts:
                    raise GlobalBudgetExhausted(
                        f'provider-attempt ceiling reached: {state["reserved"]}'
                        f'+{n} > {self.max_attempts}')
                self._write({**state, 'reserved': reserved})
                return reserved
            finally:
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def spent(self):
        return self._read()['reserved']


class GlobalBudgetExhausted(RuntimeError):
    pass


class BudgetedTransport(AuditedTransport):
    """Audited transport that charges one provider attempt per HTTP request."""

    def __init__(self, store, context, global_budget):
        super().__init__(store, context)
        self.global_budget = global_budget

    def handle_request(self, request):
        try:
            self.global_budget.reserve(1)
        except GlobalBudgetExhausted:
            self.store.event('global_budget_exhausted',
                             reserved=self.global_budget.spent(),
                             max_attempts=self.global_budget.max_attempts)
            raise
        return super().handle_request(request)


class MathFreshSolver(FreshSolver):
    def __init__(self, store, settings, api_key, resource_budget=None, global_budget=None):
        factory = (lambda: BudgetedTransport(store, self.sample, global_budget)
                   ) if global_budget is not None else None
        super().__init__(store, settings, api_key, resource_budget, transport_factory=factory)


def math_tasks(split_path: Path, section: str):
    split = json.loads(Path(split_path).read_text(encoding='utf-8'))['tasks']
    lo = 0 if section == 'dev' else 100
    hi = 100 if section == 'dev' else 500
    tasks = []
    for i in range(lo, hi):
        ex = split[i]
        if not ex.get('question') or 'gold' not in ex:
            raise ValueError(f'Split entry {i} lacks question/gold')
        tasks.append({'id': f'math500_split#{i}', 'question': ex['question'],
                      'gold': ex['gold'], 'section': section})
    if len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('Duplicate task ids')
    return tasks


def max_samples_per_call(source: Path) -> int:
    """Largest n=... sample count requested by a member's frozen source.

    Scans literal `n=<int>` arguments and `n_samples = <int>` style bindings;
    anything dynamic is bounded by the protocol ceiling of 5.
    """
    import re
    text = source.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n')
    ns = [int(m) for m in re.findall(r'\bn\s*=\s*(\d+)', text)]
    bindings = dict(re.findall(r'(\w*(?:samples?|n_samples|votes?|k)\w*)\s*=\s*(\d+)', text))
    ns.extend(int(v) for v in bindings.values())
    return min(max(ns, default=1), 5)


def per_cell_budget(config, harnesses):
    """Worst-case per-cell reservation from frozen repeat-0 call statistics
    and the member's frozen maximum sample count per logical call."""
    stats = config['call_stats']
    budgets = {}
    for h in harnesses:
        hid = h['id']
        if hid not in stats:
            raise ValueError(f'No frozen call statistics for member {hid}')
        max_n = max_samples_per_call(ROOT / h['source'])
        cap = int(math.ceil(stats[hid] * 1.5)) + 2
        budgets[hid] = {'max_logical_calls': cap,
                        'max_requested_samples': cap * max_n,
                        'max_output_tokens': cap * max_n * 32000,
                        'max_request_bytes': 4_000_000}
    return budgets


def load_panel_draw(config):
    draw_path = Path(config['panel_draw_path'])
    draw = json.loads(draw_path.read_text(encoding='utf-8'))
    entries = draw['panel']
    drawn = sorted((e[0] if isinstance(e, (list, tuple)) else e) for e in entries)
    configured = sorted(h['id'] for h in config['harnesses'])
    if configured != drawn:
        raise ValueError('Configured harnesses differ from the frozen panel draw')
    return {'panel_draw_path': draw_path.name,
            'panel_draw_sha256': file_hash(draw_path),
            'schedule_salt': draw['salt'],
            'panel': drawn,
            'eligible': sorted(draw['eligible'])}


def prepare(config):
    settings = SolverSettings(**config['solver'])
    resource_budget = ResourceBudget.from_mapping(config.get('resource_budget'))
    for field in ('worker_wall_seconds', 'drain_seconds'):
        if not math.isfinite(config[field]) or config[field] <= 0:
            raise ValueError('Worker wall and drain intervals must be finite and positive')
    if config['worker_wall_seconds'] <= config['drain_seconds']:
        raise ValueError('Worker wall must exceed its drain interval')
    if config.get('cache_mode') != 'off' or not config['acquisition_id']:
        raise ValueError('Explicit acquisition identity and cache_mode=off required')
    if not config.get('global_budget_path'):
        raise ValueError('A shared acquisition-wide global_budget_path is required')
    if config['section'] not in ('dev', 'eval'):
        raise ValueError("section must be 'dev' or 'eval'")
    if not os.environ.get(config['api_key_env']):
        raise ValueError('Provider key is absent')
    if not 1 <= config.get('concurrency', 1) <= 4:
        raise ValueError('Concurrency must be within the authorized 1..4 range')
    if (config.get('failure_window_size', 200), config.get('failure_stop_rate', 0.15)) not in ((200, 0.15), (None, None)):
        raise ValueError('Failure stop policy is frozen: window 200, rate 0.15')
    repeats = config['repeats']
    if not repeats or any(type(r) is not int or r < 0 for r in repeats) or len(set(repeats)) != len(repeats):
        raise ValueError('Expected distinct nonnegative repeats')
    panel = load_panel_draw(config)
    harnesses = []
    for h in config['harnesses']:
        source = (ROOT / h['source']).resolve()
        if not h['id'] or not source.is_relative_to(AGENTS) or not source.is_file():
            raise ValueError(f'Expected a trusted local MATH harness source: {h}')
        h = dict(h)
        h['source'] = source.relative_to(ROOT).as_posix()
        h['source_sha256_lf'] = lf_sha256(source)
        h['source_sha256_raw'] = file_hash(source)
        harnesses.append(h)
    if not harnesses or len({h['id'] for h in harnesses}) != len(harnesses):
        raise ValueError('Expected distinct harness identities')
    tasks = math_tasks(Path(config['split_path']), config['section'])
    sources = sorted(set(MATH_SOURCES))
    hashes = {str(path.relative_to(ROOT)): file_hash(path) for path in sources}
    resolved_draw = Path(config['panel_draw_path']).resolve()
    try:
        draw_key = str(resolved_draw.relative_to(ROOT))
    except ValueError:
        draw_key = str(resolved_draw)
    hashes[draw_key] = panel['panel_draw_sha256']
    from dataclasses import asdict
    manifest = {
        'version': 'math-fresh-acquisition-v1',
        'acquisition_id': config['acquisition_id'],
        'protocol': 'REAL_EVIDENCE_PROTOCOL_V1 + v1.1 amendment',
        'protocol_sha256': file_hash(config['protocol_path']),
        'missing_usage_policy': 'stop-before-next-cell-preserve-pending-v1',
        'failure_policy': {'window': 200, 'stop_rate': 0.15,
                           'unknown_requests': 'stop-and-reconcile'},
        'global_budget': {'max_provider_attempts': config['max_provider_attempts'],
                          'state_file': str(Path(config['global_budget_path'])
                                            .resolve())},
        'cache_mode': 'off',
        'solver': asdict(settings),
        'resource_budget': asdict(resource_budget) if resource_budget else None,
        'per_cell_budget': per_cell_budget(config, harnesses),
        'panel_draw': panel,
        'api_key_env': config['api_key_env'],
        'worker_wall_seconds': config['worker_wall_seconds'],
        'drain_seconds': config['drain_seconds'],
        'concurrency': config.get('concurrency', 1),
        'task_order': 'repeat-task-member-sha256-v1',
        'schedule_salt': config['schedule_salt'],
        'section': config['section'],
        'harnesses': harnesses,
        'repeats': repeats,
        'tasks_sha256': digest(tasks),
        'split_sha256': file_hash(config['split_path']),
        'source_sha256': hashes,
        'judge': 'gsm8k-collect-is-correct-v1 (LF-normalized source hash bound)',
        'temperature_semantics': 'per-call temperature is defined by each member\'s '
                                 'frozen source (same code path as repeat-0); '
                                 'bridge temp_override unused',
        'python': sys.version,
    }
    return manifest, tasks


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
    if not request.get('global_budget_path'):
        raise ValueError('Worker requires the shared global budget path')
    for key in list(os.environ):
        if key.startswith(('SOLVER_', 'SQL_SOLVER_', 'BIRD_', 'ASE_', 'TTHE_CONFIG')):
            del os.environ[key]
    folder = Path(request['folder'])
    cell = request['cell']
    # The worker's manifest binds THIS cell's per-member worst-case budget so
    # FreshSolver's manifest equality check matches what the worker enforces.
    worker_manifest = {**manifest, 'cell': cell,
                       'resource_budget': manifest['per_cell_budget'][harness['id']]}
    with RunStore(folder, worker_manifest) as store, \
            tempfile.TemporaryDirectory(prefix='bridge_', dir=folder) as temp:
        bootstrap = Path(temp) / 'config.json'
        bootstrap.write_text(json.dumps({'llm': {'provider': 'mock'},
                                         'dataset': {'name': 'bird',
                                                     'bird_root': request['dataset_root']},
                                         'output_dir': temp}), encoding='utf-8')
        os.environ['TTHE_CONFIG'] = str(bootstrap)
        os.environ['SQL_SOLVER_CACHE'] = str(Path(temp) / 'unused.json')
        sys.path.insert(0, str(TTHE))
        sys.path.insert(0, str(ROOT / 'experiment'))
        from text_to_sql import bridge
        from gsm8k.collect import is_correct
        task_key, needed = store.begin(cell)
        if not needed:
            raise RuntimeError('Worker output must be fresh; parent alone handles resume')
        budget = ResourceBudget.from_mapping(manifest['per_cell_budget'][harness['id']])
        global_budget = GlobalBudget(Path(request['global_budget_path']),
                                     manifest['global_budget']['max_provider_attempts'])
        solver = MathFreshSolver(store, SolverSettings(**manifest['solver']), api_key,
                                 budget, global_budget=global_budget)

        def frozen(prompt, system='', temperature=0., n=1, seq=0):
            override = getattr(bridge._tls, 'temp_override', None)
            if override is not None:
                # Protocol v1.2 A8: sampling temperature is defined by each
                # member's frozen source; thread-local overrides are forbidden.
                store.event('run_invalid', task=task_key, reason='temp_override_used')
                raise RuntimeError('bridge.temp_override is forbidden under protocol v1.2')
            return solver(prompt, system, temperature, n, seq)

        bridge.solver_llm = frozen
        base_threads = set(threading.enumerate())
        try:
            with solver.bind(task_key):
                # Load from the manifest source path under a unique module name
                # inside the gsm8k.agents package, so the members' relative
                # `..harness_base` import resolves and identical clone sources
                # keep distinct module identities.
                import gsm8k.agents  # noqa: F401  (parent package for relative imports)
                name = 'gsm8k.agents._iso_' + digest(harness)[:12]
                spec = importlib.util.spec_from_file_location(name, ROOT / harness['source'])
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                classes = [v for v in vars(module).values()
                           if isinstance(v, type) and v.__name__ != 'MathHarness'
                           and v.__module__ == module.__name__
                           and any(c.__name__ == 'MathHarness' for c in v.__mro__)]
                if len(classes) != 1:
                    raise ValueError('Expected exactly one MathHarness subclass')
                instance = classes[0]()
                started = time.monotonic()
                answer = instance.solve(task['question'])
                answer_seconds = time.monotonic() - started
                if not isinstance(answer, str):
                    answer = '' if answer is None else str(answer)
                store.event('answer_returned', task=task_key, final_answer=answer[-2000:],
                            answer_seconds=answer_seconds)
                drain_deadline = time.monotonic() + manifest['drain_seconds']
                while set(threading.enumerate()) - base_threads:
                    if time.monotonic() >= drain_deadline:
                        store.event('drain_expired', task=task_key, local_threads='pending',
                                    provider_completion='unknown')
                        os._exit(3)
                    time.sleep(0.01)
            if lf_sha256(ROOT / harness['source']) != harness['source_sha256_lf']:
                store.event('run_invalid', task=task_key, reason='harness_source_changed')
                raise RuntimeError('Harness source changed')
            store.finish(task_key, {**cell, 'final_answer': answer[-2000:],
                                    'answer_seconds': answer_seconds,
                                    'official_correct': int(bool(is_correct(answer, task['gold']))),
                                    'n_llm_calls': len(instance._trace),
                                    'trace': instance._trace})
        except Exception as exc:
            store.event('task_error', task=task_key, error_type=type(exc).__name__)
            raise
        finally:
            solver.close()


def run_math_worker(request_path, folder, wall_seconds):
    """isolated_collect.run_worker twin that launches THIS module as the worker."""
    folder = Path(folder)
    gate = folder / ('start-' + uuid.uuid4().hex)
    command = [sys.executable, '-m', 'experiment.revision.fresh_collect_math',
               '--worker', str(request_path), '--gate', str(gate)]
    with (folder / 'stdout.txt').open('wb') as stdout, (folder / 'stderr.txt').open('wb') as stderr, \
            WindowsJob() as job:
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
                    job.wait_empty(seconds=1)
                except RuntimeError:
                    reason = 'descendants_survived' if reason == 'exited' else reason
                    job.terminate()
            after = job.wait_empty()
            return {'pid': process.pid, 'exit_code': process.returncode, 'reason': reason,
                    'wall_seconds': time.monotonic() - started, 'before_cleanup': before,
                    'after_cleanup': after}
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if job.accounting()['active_processes']:
                job.terminate()
                job.wait_empty()
            process.close()


def _snapshot(store, output, reason, **fields):
    store.event('acquisition_stopped', reason=reason, **fields)
    (Path(output) / 'snapshot.json').write_text(
        json.dumps(store.snapshot(), indent=2, ensure_ascii=False), encoding='utf-8')


def _child_requests_closed(child):
    """True when every provider request in the child ledger reached a known
    outcome (same predicate RunStore.finish enforces), so the failure is fully
    accounted and can be recorded without hiding unknown requests."""
    if not child:
        return False
    events = child.get('events', [])
    logical = {e['id'] for e in events if e.get('kind') == 'logical_start'}
    if not logical:
        return False
    starts = {e['id'] for e in events if e.get('kind') == 'http_start'}
    ends = {e.get('attempt') for e in events if e.get('kind') == 'http_end'}
    closed = {e.get('logical') for e in events
              if e.get('kind') in ('logical_end', 'logical_error')}
    bad = any(e.get('kind') in ('http_unknown', 'drain_expired',
                                'resource_budget_rejected') for e in events)
    return not bad and starts == ends and logical == closed


def _run_cell(store, manifest, config, cell, task, harness):
    """Execute one cell; returns True on success, False on a closed-request
    failure counted against the sliding stop window. Raises on unknown
    requests, budget exhaustion, or infrastructure stop conditions."""
    key, needed = store.begin(cell)
    if not needed:
        # A resumed error cell keeps counting as a failure for the stop policy.
        old = store.result_of(key)
        if old is not None and old.get('official_correct') is None:
            return False
        return True
    folder = Path(config['output']).resolve() / 'workers' / key
    folder.mkdir(parents=True, exist_ok=False)
    request = {'manifest': manifest, 'cell': cell, 'task': task, 'harness': harness,
               'folder': str(folder),
               'dataset_root': str(Path(config['dataset_root']).resolve()),
               'global_budget_path': str(Path(config['global_budget_path']).resolve())}
    request_path = folder / 'request.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
    process = run_math_worker(request_path, folder, manifest['worker_wall_seconds'])
    store.event('worker_exited', task=key, **process)
    try:
        child = read_ledger(folder)
    except Exception as exc:  # noqa: BLE001
        store.event('ledger_read_error', task=key, error_type=type(exc).__name__,
                    request_accounting='unknown')
        child = None
    if child:
        import_events(store, key, child)
    success = (process['reason'] == 'exited' and process['exit_code'] == 0
               and child and len(child['tasks']) == 1
               and child['tasks'][0]['result'] is not None)
    if not success:
        child_events = (child or {}).get('events', [])
        if any(e.get('kind') == 'global_budget_exhausted' for e in child_events):
            _snapshot(store, config['output'], 'provider_attempt_ceiling_reached', task=key)
            raise RuntimeError('provider-attempt ceiling reached; acquisition stopped '
                               'at the frozen GlobalBudget limit')
        if not _child_requests_closed(child):
            _snapshot(store, config['output'], 'unknown_requests_preserved', task=key)
            raise RuntimeError('Worker has unknown or unresolved provider requests; '
                               'reconcile the request ledger before any new acquisition')
        # Fully accounted failure: record an error result so the cell is
        # durable, resumes cleanly, and counts against the sliding stop window.
        error_types = [e.get('error_type') for e in child.get('events', [])
                       if e.get('kind') == 'task_error']
        attempts = [e.get('attempt') for e in child.get('events', [])
                    if e.get('kind') == 'http_start']
        store.finish(key, {**cell, 'error': error_types or [process['reason']],
                           'official_correct': None, 'final_answer': None,
                           'provider_attempts': len(attempts)})
        store.event('cell_failed', task=key, worker_reason=process['reason'],
                    exit_code=process['exit_code'])
        return False
    child_result = child['tasks'][0]['result']
    accounting = child_result.get('accounting', {})
    if accounting.get('responses_missing_usage') != 0 or accounting.get('total_tokens') is None:
        _snapshot(store, config['output'], 'response_usage_unknown', task=key,
                  answer_preserved=True, worker_result=child_result)
        raise RuntimeError('Response usage unknown; preserve answer and pending cell, '
                           'do not retry automatically')
    store.finish(key, {**child_result, 'worker_pid': process['pid']})
    return True


def collect(config):
    manifest, tasks = prepare(config)
    output = Path(config['output']).resolve()
    # One acquisition-wide attempt pool shared by every arm (real/clone/dev)
    # and every shard, per protocol v1.2 A2.
    global_budget = GlobalBudget(Path(config['global_budget_path']),
                                 manifest['global_budget']['max_provider_attempts'])
    by_task = {t['id']: t for t in tasks}
    by_harness = {h['id']: h for h in manifest['harnesses']}
    rows = schedule(manifest['repeats'], manifest['harnesses'], tasks,
                    config['schedule_salt'])
    shard_index = config.get('shard_index', 0)
    shards = config.get('shards', 1)
    rows = [row for i, row in enumerate(rows) if i % shards == shard_index]
    manifest['schedule_sha256'] = digest(rows)
    manifest['shard'] = {'index': shard_index, 'count': shards}
    concurrency = config.get('concurrency', 1)
    window = deque(maxlen=manifest['failure_policy']['window'])
    stop = {'reason': None}
    state_lock = threading.Lock()

    def run_one(cell):
        if stop['reason']:
            return None
        try:
            ok = _run_cell(store, manifest, config, cell, by_task[cell['task']],
                           by_harness[cell['harness']])
        except Exception as exc:  # noqa: BLE001  (stop conditions are protocol states)
            with state_lock:
                stop['reason'] = f'{type(exc).__name__}: {exc}'
            return None
        with state_lock:
            window.append(ok)
            if len(window) == window.maxlen and sum(1 for v in window if v is False) > 0.15 * len(window):
                stop['reason'] = 'failure_window_exceeded'
                return None
        return ok

    with RunStore(output, manifest) as store:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            outcomes = list(pool.map(run_one, rows))
        if stop['reason']:
            _snapshot(store, output, stop['reason'],
                      completed=sum(1 for o in outcomes if o is True),
                      failed=sum(1 for o in outcomes if o is False))
            raise RuntimeError(f'Acquisition stopped: {stop["reason"]}')
        attempted = [o for o in outcomes if o is not None]
        if attempted and sum(1 for o in attempted if o is False) > 0.15 * len(attempted):
            _snapshot(store, output, 'overall_failure_rate_exceeded',
                      completed=sum(1 for o in attempted if o is True),
                      failed=sum(1 for o in attempted if o is False))
            raise RuntimeError('Acquisition sealed nothing: overall failure rate '
                               'exceeds the frozen 0.15 stop rate')
        validate_inputs(store, manifest['source_sha256'])
        store.event('run_verified', cells=len(rows),
                    provider_attempts=global_budget.spent())
        result = store.snapshot()
        (output / 'snapshot.json').write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                              encoding='utf-8')
        return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', help='parent only: acquisition config json')
    ap.add_argument('--worker', help='internal: run one cell as a worker process')
    ap.add_argument('--gate', help='internal: worker start gate file')
    args = ap.parse_args()
    if args.worker:
        worker(json.loads(Path(args.worker).read_text(encoding='utf-8')), args.gate)
        return
    if not args.config:
        ap.error('--config is required unless running as a worker')
    collect(json.loads(Path(args.config).read_text(encoding='utf-8')))


if __name__ == '__main__':
    main()
