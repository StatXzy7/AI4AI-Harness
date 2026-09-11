"""Source-assigned response profiles with real in-memory SQLite execution.

These exposed-candidate diagnostics retain requests, not admission decisions.
Profile choice must precede measurement; unsupported requests remain explicit.
"""
from __future__ import annotations

from contextlib import closing
import copy
import json
import re
import sqlite3

from experiment.revision.gate_v3 import QUESTION, SQL_A, SQL_B, SQL_C

CURRENT_FIELD = 'Current sub-question to answer:'
STEPS = ['List ledger identifiers.', 'List ledger amounts.']


def settings():
    """Fixed full scenario list; no selection based on diagnostic outcomes."""
    return [
        dict(strategy='schema_link', name='ledger_json',
             linking=dict(tables=['ledger'], columns=['ledger.id']), final=SQL_A),
        dict(strategy='schema_link', name='unused_json',
             linking=dict(tables=['unused'], columns=['unused.label']), final='SELECT label FROM unused'),
        dict(strategy='schema_link', name='malformed_json', linking=None, final=SQL_A),
        *[dict(strategy='decompose', name=f'parts_{i}', steps=STEPS,
               answers=[f'{SQL_A} /* payload_{i}_0 */', f'{SQL_B} /* payload_{i}_1 */'],
               final=(SQL_A, SQL_B)[i]) for i in range(2)],
        dict(strategy='error_classify', name='success', initial=SQL_A),
        dict(strategy='error_classify', name='sqlite_syntax', initial='SELEC id FROM ledger'),
        dict(strategy='error_classify', name='sqlite_missing_column', initial='SELECT absent FROM ledger'),
        dict(strategy='error_classify', name='sqlite_missing_table', initial='SELECT id FROM absent'),
        dict(strategy='error_classify', name='sqlite_incomplete', initial='SELECT id FROM'),
        dict(strategy='error_classify', name='executable_other_column', initial=SQL_B),
    ]


def current_step(prompt, steps):
    """Resolve the predeclared dedicated field; full-plan mentions are context."""
    fields = re.findall(r'(?m)^' + re.escape(CURRENT_FIELD) + r'\s*\n([^\n]+)', prompt)
    if len(fields) != 1:
        return None
    exact = [i for i, step in enumerate(steps) if fields[0].strip() == step]
    return exact[0] if len(exact) == 1 else None


class ResponseIO:
    def __init__(self, case, database):
        self.case = case
        self.database = database
        self.trace = []
        self.calls = 0
        self.issues = []
        self.last_error = None

    def llm(self, prompt, system='', temperature=0., n=1):
        if n != 1 or not isinstance(prompt, str) or not isinstance(system, str):
            raise ValueError('profile supports single text requests only')
        if self.calls >= 12:
            raise RuntimeError('profile call limit exceeded')
        case = self.case
        role = None
        target = None
        text = system + '\n' + prompt
        if case['strategy'] == 'schema_link':
            role = 'linking_json' if self.calls == 0 else 'final_sql'
            response = ('not JSON' if case['linking'] is None else json.dumps(case['linking'])) if self.calls == 0 else case['final']
            if self.calls > 1:
                self.issues.append('unexpected extra schema-link request')
        elif case['strategy'] == 'decompose':
            if self.calls == 0:
                role, response = 'plan', json.dumps(case['steps'])
            else:
                target = current_step(prompt, case['steps'])
                if target is not None:
                    role, response = 'subquestion_sql', case['answers'][target]
                elif CURRENT_FIELD in prompt:
                    role, response = 'unresolved_subquestion', SQL_C
                    self.issues.append('dedicated current-subquestion field absent or ambiguous')
                elif all(answer in text for answer in case['answers']):
                    role, response = 'assembly_sql', case['final']
                else:
                    role, response = 'unresolved_request', SQL_C
                    self.issues.append('request has neither assigned target nor all partial answers')
        else:
            role = 'initial_sql' if self.calls == 0 else 'repair_sql'
            response = case['initial'] if self.calls == 0 else (SQL_A if self.last_error and self.last_error in text else case['initial'])
        self.calls += 1
        self.trace.append(dict(kind='llm', prompt=prompt, system=system, temperature=temperature,
                               n=n, response=response, response_role=role, target_step=target))
        return response

    def execute(self, sql):
        try:
            rows = self.database.execute(sql).fetchall()
            result = dict(ok=True, rows=[list(row) for row in rows], error=None)
        except sqlite3.Error as exc:
            result = dict(ok=False, rows=[], error=str(exc), error_type=type(exc).__name__)
        self.last_error = result['error']
        self.trace.append(dict(kind='execute', sql=sql, **copy.deepcopy(result)))
        return result


def run(solve, case):
    with closing(sqlite3.connect(':memory:')) as db:
        db.executescript('CREATE TABLE ledger(id INTEGER, amount REAL);'
                         'INSERT INTO ledger VALUES(1,10),(2,20);'
                         'CREATE TABLE unused(label TEXT); INSERT INTO unused VALUES("z");')
        io = ResponseIO(case, db)
        final = None
        error = None
        try:
            final = solve(io, QUESTION)
            if not isinstance(final, str) or not final.strip():
                raise TypeError('nonempty final SQL required')
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        return dict(case=case, final=final, trace=io.trace, error=error,
                    interface_issues=io.issues, admission='not_evaluated',
                    scope='source-assigned exposed-candidate interface diagnostic; not calibration')
