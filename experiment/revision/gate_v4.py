"""Unified development measurement, with explicit source-assigned response roles.

Frozen v3 supplies five unchanged strategy probes. Typed schema/decomposition and
real SQLite feedback supply the remaining three. This module never admits a
candidate: semantic decisions and independently frozen reference checks remain
separate. Unsupported response profiles are review-required, not rejection.
"""
from __future__ import annotations

import copy

from experiment.revision import gate_v3
from experiment.revision.runtime_response_profiles import run, settings

STRATEGIES = gate_v3.STRATEGIES
PROFILES = {
    'schema_link': ('tables_columns_json',),
    'decompose': ('dedicated_current_subquestion',),
    'error_classify': ('local_classifier', 'llm_classifier'),
}


class CategoryReply:
    """Supply a source-declared intermediate category after a real failed execute."""
    def __init__(self, io, category):
        self.io = io
        self.category = category
        self.pending = False

    @property
    def trace(self):
        return self.io.trace

    @property
    def schema(self):
        return gate_v3.SCHEMA

    def llm(self, prompt, system='', temperature=0., n=1):
        if not self.pending:
            return self.io.llm(prompt, system=system, temperature=temperature, n=n)
        if type(n) is not int or n != 1 or not isinstance(prompt, str) or not isinstance(system, str):
            raise ValueError('category profile requires a single text request')
        if self.io.calls >= 12:
            raise RuntimeError('profile call limit exceeded')
        self.pending = False
        self.io.calls += 1
        self.io.trace.append(dict(kind='llm', prompt=prompt, system=system, temperature=temperature,
                                  n=n, response=self.category, response_role='classification', target_step=None))
        return self.category

    def execute(self, sql):
        result = self.io.execute(sql)
        self.pending = not result['ok']
        return result


def typed_scenarios(strategy, profile):
    cases = [copy.deepcopy(c) for c in settings() if c['strategy'] == strategy]
    if strategy == 'error_classify':
        categories = {'success': None, 'executable_other_column': None,
                      'sqlite_syntax': 'syntax', 'sqlite_incomplete': 'syntax',
                      'sqlite_missing_column': 'schema', 'sqlite_missing_table': 'schema'}
        for case in cases:
            case['category_reply'] = categories[case['name']]
        # Numeric overflow is an execution-time failure distinct from name/syntax
        # resolution. It probes the declared residual category, not answer truth.
        cases.append(dict(strategy=strategy, name='sqlite_numeric_overflow',
                          initial='SELECT abs(-9223372036854775808)', category_reply='semantics'))
        if profile == 'llm_classifier':
            for label, reply in [('invalid', 'unrecognized category'), ('ambiguous', 'syntax or schema')]:
                case = copy.deepcopy(next(c for c in cases if c['name'] == 'sqlite_syntax'))
                case.update(name='category_' + label, category_reply=reply, diagnostic_only=True)
                cases.append(case)
    return cases


def evaluate(solve, strategy, *, profile=None, salt='v4dev'):
    """Return versioned observations. Profile choice must precede execution."""
    if strategy not in STRATEGIES:
        raise ValueError('unknown strategy')
    if strategy not in PROFILES:
        if profile is not None:
            raise ValueError('no response profile used by this strategy')
        result = gate_v3.evaluate(solve, strategy, salt=salt)
        return dict(version='gate-v4', strategy=strategy, profile=None,
                    structural_verdict=result['verdict'], runs=result['runs'],
                    admission='not_evaluated', scope=__doc__)
    if profile not in PROFILES[strategy]:
        return dict(version='gate-v4', strategy=strategy, profile=profile,
                    structural_verdict='review_required', runs=[],
                    interface_issues=['source response profile unsupported or not assigned'],
                    admission='not_evaluated', scope=__doc__)
    observations = []
    for case in typed_scenarios(strategy, profile):
        def measured(io, question, case=case):
            io.schema = gate_v3.SCHEMA
            interface = CategoryReply(io, case['category_reply']) if profile == 'llm_classifier' else io
            return solve(interface, question)
        result = run(measured, case)
        # Full-schema context is not a rejection condition. Typed traces require
        # independent dataflow/action review even when all requests resolve.
        result['status'] = 'review_required'
        observations.append(result)
    return dict(version='gate-v4', strategy=strategy, profile=profile,
                structural_verdict='review_required', runs=observations,
                admission='not_evaluated', scope=__doc__)
