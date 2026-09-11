"""Finite response-role observations for exposed error-classification controls.

This development component never admits a harness. Roles must be assigned from
source before measurement; supplying a correct category is not classification
accuracy evidence. The frozen gate-v3 implementation remains unchanged.
"""
from __future__ import annotations

import copy

from experiment.revision import gate_v3

PROFILES = ('direct_repair', 'classify_then_repair')
OBSERVATIONAL_REASONS = {
    'unambiguous_error_class_not_observed',
    'classification_action_semantics_review_required',
}


class ClassificationIO(gate_v3.ProbeIO):
    """Script one initial execution and a fixed post-failure response sequence."""

    def __init__(self, probe, profile, category_reply=None):
        if probe.strategy != 'error_classify' or profile not in PROFILES:
            raise ValueError('requires an error_classify probe and explicit profile')
        super().__init__(probe)
        self.profile = profile
        self.category_reply = probe.error_class if category_reply is None else category_reply
        self.state = 'initial'
        self.interface_issues = []

    def llm(self, prompt, system='', temperature=0., n=1):
        if not isinstance(prompt, str) or not isinstance(system, str):
            raise TypeError('solver prompt/system must be text')
        if type(n) is not int or n < 1:
            raise ValueError('invalid n')
        if self.samples + n > 12:
            raise RuntimeError('probe solver-call limit exceeded')
        before = self.state
        if before == 'initial':
            role = 'initial_sql'
            values = [self.probe.responses[min(j, len(self.probe.responses) - 1)] for j in range(n)]
            self.state = 'awaiting_initial_execution'
        elif before == 'after_failure' and self.profile == 'classify_then_repair':
            role = 'classification'
            values = [self.category_reply] * n
            self.state = 'after_category'
        elif before in ('after_failure', 'after_category'):
            role = 'repair_sql'
            feedback_carried = self.probe.error and self.probe.error in prompt + system
            values = [self.probe.expected if feedback_carried else gate_v3.SQL_C] * n
            self.state = 'after_repair'
        else:
            role = 'unsupported'
            values = [gate_v3.SQL_C] * n
            self.interface_issues.append(f'LLM request in state {before}')
            self.state = 'unsupported'
        self.samples += n
        result = values if n > 1 else values[0]
        self.trace.append(dict(kind='llm', prompt=prompt, system=system, n=n,
                               temperature=temperature, response=copy.deepcopy(result),
                               response_role=role, state_before=before, state_after=self.state))
        return result

    def execute(self, sql):
        before = self.state
        result = super().execute(sql)
        if before == 'awaiting_initial_execution':
            self.state = 'after_success' if result['ok'] else 'after_failure'
        elif before == 'after_repair':
            self.state = 'after_repair_execution'
        else:
            self.interface_issues.append(f'execute request in state {before}')
            self.state = 'unsupported'
        self.trace[-1].update(state_before=before, state_after=self.state)
        return result


def run_profile(solve, probe, profile, category_reply=None):
    """Collect a trace and old structural flags; never issue an admission label."""
    io = ClassificationIO(probe, profile, category_reply)
    final = None
    error = None
    reasons = []
    try:
        final = solve(io, probe.question)
        if not isinstance(final, str) or not final.strip():
            raise TypeError('solve must return a nonempty SQL string')
        reasons = gate_v3.assess(probe, final, io.trace)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    hard = [reason for reason in reasons if reason not in OBSERVATIONAL_REASONS]
    # An unsupported response sequence cannot establish the SQL counterfactual.
    if io.interface_issues:
        hard = [reason for reason in hard if reason != 'counterfactual_output_mismatch']
    return dict(probe=probe.name, profile=profile, category_reply=io.category_reply,
                status='review_required', structural_failures=hard, observations=reasons,
                interface_issues=io.interface_issues, final=final, error=error,
                trace=io.trace, end_state=io.state)
