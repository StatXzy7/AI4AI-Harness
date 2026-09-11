"""Versioned fresh solver and durable acquisition ledger; no shared response cache.

SDK retries and redirects are disabled. Explicit status retries are recorded;
transport failures are not retried because provider completion/cost is unknown.
This runtime is for trusted, frozen harnesses, not an untrusted-code sandbox.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import hashlib
import json
import msvcrt
from pathlib import Path
import sqlite3
import threading
import time

import httpx
from openai import APIStatusError, OpenAI


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


class RunStore:
    """One process owns an acquisition; SQLite commits preserve every request boundary."""
    def __init__(self, folder, manifest):
        self.folder = Path(folder)
        self.manifest = json.loads(canonical(manifest))
        self.run_id = digest(manifest)
        self.mutex = threading.Lock()

    def __enter__(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock_file = (self.folder / 'writer.lock').open('a+b')
        self.lock_file.seek(0)
        try:
            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.lock_file.close()
            raise RuntimeError('Acquisition already has a writer') from None
        try:
            self.db = sqlite3.connect(self.folder / 'ledger.sqlite', check_same_thread=False)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS manifest (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT)')
            self.db.execute('CREATE TABLE IF NOT EXISTS tasks (key TEXT PRIMARY KEY, result TEXT)')
            self.db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, value TEXT)')
            self.db.execute("CREATE INDEX IF NOT EXISTS events_task ON events(json_extract(value,'$.task'))")
            old = self.db.execute('SELECT value FROM manifest WHERE id=1').fetchone()
            if old is None:
                self.db.execute('INSERT INTO manifest VALUES (1,?)', (canonical(self.manifest),))
                self.db.commit()
            elif old[0] != canonical(self.manifest):
                raise ValueError('Run identity changed; use a separate acquisition output')
            if self.db.execute("SELECT 1 FROM events WHERE json_extract(value,'$.kind')='run_invalid' LIMIT 1").fetchone():
                raise RuntimeError('Acquisition marked invalid; do not reuse its completed rows')
            if self.db.execute('SELECT key FROM tasks WHERE result IS NULL LIMIT 1').fetchone():
                raise RuntimeError('Unfinished task: reconcile its request ledger before any new acquisition')
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_args):
        if hasattr(self, 'db'):
            self.db.close()
        self.lock_file.seek(0)
        msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        self.lock_file.close()

    def event(self, kind, **fields):
        with self.mutex, self.db:
            value = {'kind': kind, 'time_ns': time.time_ns(), **fields}
            return self.db.execute('INSERT INTO events(value) VALUES (?)', (canonical(value),)).lastrowid

    def begin(self, identity):
        key = digest({'run': self.run_id, 'cell': identity})
        with self.mutex, self.db:
            old = self.db.execute('SELECT result FROM tasks WHERE key=?', (key,)).fetchone()
            if old is not None:
                if old[0] is None:
                    raise RuntimeError('Task already started without a durable final result')
                return key, False
            self.db.execute('INSERT INTO tasks VALUES (?,NULL)', (key,))
        self.event('task_start', task=key, identity=identity)
        return key, True

    def finish(self, key, result):
        with self.mutex, self.db:
            if self.db.execute("SELECT 1 FROM events WHERE json_extract(value,'$.kind')='run_invalid' LIMIT 1").fetchone():
                raise RuntimeError('Acquisition invalid; cannot finish another task')
            events = [{'id': i, **json.loads(v)} for i, v in self.db.execute(
                "SELECT id,value FROM events WHERE json_extract(value,'$.task')=? ORDER BY id", (key,))]
            starts = {e['id'] for e in events if e['kind'] == 'http_start'}
            ends = [e for e in events if e['kind'] == 'http_end']
            logical = {e['id'] for e in events if e['kind'] == 'logical_start'}
            closed = {e['logical'] for e in events if e['kind'] in ('logical_end', 'logical_error')}
            if (any(e['kind'] in ('http_unknown', 'resource_budget_rejected') for e in events)
                    or starts != {e['attempt'] for e in ends} or len(starts) != len(ends)
                    or logical != closed):
                raise RuntimeError('Task has unknown, budget-rejected, or unfinished requests; do not mark it complete')
            usage = [e['usage'] for e in ends]
            def known(item):
                return (isinstance(item, dict) and
                        all(type(item.get(k)) is int and item[k] >= 0
                            for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')))
            result = {**result, 'accounting': {
                'logical_calls': len(logical),
                'requested_samples': sum(e['n'] for e in events if e['kind'] == 'logical_start'),
                'http_attempts': len(starts), 'responses_missing_usage': sum(not known(u) for u in usage),
                'known_total_tokens': sum(u['total_tokens'] for u in usage if known(u)),
                'total_tokens': sum(u['total_tokens'] for u in usage) if all(known(u) for u in usage) else None,
                'reserved_output_tokens': sum(e.get('requested_output_tokens', 0)
                                             for e in events if e['kind'] == 'logical_start'),
                'reserved_request_bytes': sum(e.get('requested_request_bytes', 0)
                                             for e in events if e['kind'] == 'logical_start'),
                'dollar_cost': None}}
            changed = self.db.execute('UPDATE tasks SET result=? WHERE key=? AND result IS NULL',
                                      (canonical(result), key)).rowcount
            if changed != 1:
                raise RuntimeError('Task is not pending')

    def snapshot(self):
        with self.mutex:
            return {'manifest': self.manifest, 'run_id': self.run_id,
                    'tasks': [{'key': k, 'result': json.loads(v) if v is not None else None}
                              for k, v in self.db.execute('SELECT key,result FROM tasks ORDER BY key')],
                    'events': [{'id': i, **json.loads(v)}
                               for i, v in self.db.execute('SELECT id,value FROM events ORDER BY id')]}


@dataclass(frozen=True)
class ResourceBudget:
    """Per-cell request ceiling enforced before a provider request is sent."""

    max_logical_calls: int
    max_requested_samples: int
    max_output_tokens: int
    max_request_bytes: int = 1_000_000

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in (
                self.max_logical_calls, self.max_requested_samples,
                self.max_output_tokens, self.max_request_bytes)):
            raise ValueError('Resource budget limits must be positive integers')

    @classmethod
    def from_mapping(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError('resource_budget must be an object')
        return cls(**value)


@dataclass(frozen=True)
class SolverSettings:
    base_url: str
    model: str
    thinking_style: str = 'none'
    reasoning_effort: str = 'high'
    temperature_override: float | None = None
    max_tokens: int = 32000
    timeout_seconds: float = 60
    status_retries: int = 0
    retry_delay_seconds: float = 1

    def __post_init__(self):
        if self.thinking_style not in ('none', 'deepseek'):
            raise ValueError('Unsupported thinking style')
        if self.max_tokens < 1 or self.timeout_seconds <= 0 or self.status_retries < 0 or self.retry_delay_seconds < 0:
            raise ValueError('Invalid request/retry budget')
        url = httpx.URL(self.base_url)
        if url.username or url.password or url.query or url.fragment:
            raise ValueError('Endpoint must not contain credentials, query or fragment')


class AuditedTransport(httpx.BaseTransport):
    def __init__(self, store, context):
        self.store, self.context = store, context
        self.transport = httpx.HTTPTransport(retries=0)

    def handle_request(self, request):
        context = self.context.get()
        if context is None:
            raise RuntimeError('HTTP request lacks a task/sample identity')
        attempt = self.store.event('http_start', **context, method=request.method,
                                   url=str(request.url), request=json.loads(request.content))
        try:
            response = self.transport.handle_request(request)
            response.read()
        except Exception as exc:
            self.store.event('http_unknown', **context, attempt=attempt, error_type=type(exc).__name__,
                             provider_completion='unknown', usage=None)
            raise
        try:
            body = json.loads(response.content)
        except (ValueError, UnicodeError):
            body = None
        if not isinstance(body, dict):
            body = None
        self.store.event('http_end', **context, attempt=attempt, status=response.status_code,
                         response_id=body.get('id') if body else None,
                         request_id=response.headers.get('x-request-id'),
                         usage=body.get('usage') if body else None,
                         response=body, response_sha256=hashlib.sha256(response.content).hexdigest())
        return response

    def close(self):
        self.transport.close()


class FreshSolver:
    def __init__(self, store, settings, api_key, resource_budget=None):
        if store.manifest['solver'] != asdict(settings) or store.manifest['cache_mode'] != 'off':
            raise ValueError('Solver differs from the acquisition manifest')
        manifest_budget = ResourceBudget.from_mapping(store.manifest.get('resource_budget'))
        if manifest_budget != resource_budget:
            raise ValueError('Resource budget differs from the acquisition manifest')
        self.store, self.settings = store, settings
        self.resource_budget = resource_budget
        self.budget_lock = threading.Lock()
        self.reserved_logical_calls = 0
        self.reserved_samples = 0
        self.reserved_output_tokens = 0
        self.reserved_request_bytes = 0
        # Collector executes one task at a time. Harness-created joined threads
        # share that task; n-sample workers still carry their own sample context.
        self.task = None
        self.active = False
        self.binding_lock = threading.Lock()
        self.sample = ContextVar('sample', default=None)
        self.client = OpenAI(api_key=api_key, base_url=settings.base_url, max_retries=0,
                             timeout=settings.timeout_seconds,
                             http_client=httpx.Client(transport=AuditedTransport(store, self.sample),
                                                      follow_redirects=False, trust_env=False))

    def close(self):
        self.client.close()

    @contextmanager
    def bind(self, task):
        if not self.binding_lock.acquire(blocking=False):
            raise RuntimeError('FreshSolver supports one bound task at a time')
        if self.task is not None:
            self.binding_lock.release()
            raise RuntimeError('Solver task identity is immutable; create a solver for the next task')
        self.task = task
        self.active = True
        try:
            yield
        finally:
            self.active = False
            self.binding_lock.release()

    def __call__(self, prompt, system='', temperature=0.0, n=1, seq=0):
        task = self.task
        if task is None or not self.active:
            self.store.event('run_invalid', task=task, reason='solver_called_outside_its_task')
            raise RuntimeError('Solver task is not active; late request rejected')
        if not isinstance(n, int) or n < 1:
            raise ValueError('Solver needs a bound task and a positive integer sample count')
        settings = self.settings
        effective = settings.temperature_override if settings.temperature_override is not None else temperature
        reserved_output_tokens = n * settings.max_tokens
        kwargs = {'model': settings.model, 'messages': [{'role': 'system', 'content': system},
                                                       {'role': 'user', 'content': prompt}],
                  'max_tokens': settings.max_tokens}
        if settings.thinking_style == 'deepseek':
            kwargs['extra_body'] = {'thinking': {'type': 'enabled'}, 'reasoning_effort': settings.reasoning_effort}
        else:
            kwargs['temperature'] = effective
        request_bytes = len(canonical(kwargs).encode('utf-8'))
        budget = self.resource_budget
        if budget is not None:
            with self.budget_lock:
                next_calls = self.reserved_logical_calls + 1
                next_samples = self.reserved_samples + n
                next_output_tokens = self.reserved_output_tokens + reserved_output_tokens
                next_request_bytes = self.reserved_request_bytes + n * request_bytes
                if (next_calls > budget.max_logical_calls
                        or next_samples > budget.max_requested_samples
                        or next_output_tokens > budget.max_output_tokens
                        or next_request_bytes > budget.max_request_bytes):
                    self.store.event(
                        'resource_budget_rejected', task=task, seq=seq, n=n,
                        requested_output_tokens=reserved_output_tokens,
                        reserved_logical_calls=self.reserved_logical_calls,
                        reserved_samples=self.reserved_samples,
                        reserved_output_tokens=self.reserved_output_tokens,
                        reserved_request_bytes=self.reserved_request_bytes,
                        requested_request_bytes=n * request_bytes,
                        limits=asdict(budget))
                    raise RuntimeError('Per-cell resource budget exhausted before provider request')
                self.reserved_logical_calls = next_calls
                self.reserved_samples = next_samples
                self.reserved_output_tokens = next_output_tokens
                self.reserved_request_bytes = next_request_bytes
        logical = self.store.event('logical_start', task=task, n=n, seq=seq, cache_hit=False,
                                   requested_temperature=temperature, effective_temperature=effective,
                                   transmitted_temperature=kwargs.get('temperature'), request=kwargs,
                                   requested_output_tokens=reserved_output_tokens,
                                   requested_request_bytes=n * request_bytes)

        def one(index):
            token = self.sample.set({'task': task, 'logical': logical, 'sample': index})
            try:
                for retry in range(settings.status_retries + 1):
                    try:
                        response = self.client.chat.completions.create(**kwargs)
                        message = response.choices[0].message
                        return message.content or getattr(message, 'reasoning_content', '') or ''
                    except APIStatusError as exc:
                        if exc.status_code not in (429, 500, 502, 503, 504) or retry == settings.status_retries:
                            raise
                        self.store.event('status_retry', task=task, logical=logical, sample=index,
                                         retry=retry + 1, status=exc.status_code)
                        time.sleep(settings.retry_delay_seconds)
            finally:
                self.sample.reset(token)
        try:
            # Context is bound explicitly inside each worker; no abandoned timeout pool.
            with ThreadPoolExecutor(max_workers=n) as pool:
                outputs = list(pool.map(one, range(n)))
            self.store.event('logical_end', task=task, logical=logical, outputs=outputs)
            return outputs[0] if n == 1 else outputs
        except Exception as exc:
            self.store.event('logical_error', task=task, logical=logical, error_type=type(exc).__name__)
            raise
