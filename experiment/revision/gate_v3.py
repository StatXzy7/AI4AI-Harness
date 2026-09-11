"""Development gate-v3 instrument. Synthetic probes only; never benchmark labels.

Versioned copy of frozen v2: preserve old measurements while repairing request
attribution and treating category keywords as observations, not hard verdicts.

This is a versioned observable contract, not a general semantic verifier. A
passing development control is not independent calibration or release approval.
Callables use solve(io, question); production SQLHarness adaptation is separate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable

STRATEGIES = ('repair', 'vote3', 'schema_link', 'hint_guard', 'two_view',
              'decompose', 'error_classify', 'format_guard')
SCHEMA = 'Table ledger(id, amount)\nTable unused(label)'
QUESTION = 'Return ledger identifiers.'
SQL_A = 'SELECT id FROM ledger'
SQL_B = 'SELECT amount FROM ledger'
SQL_C = 'SELECT id FROM ledger WHERE id > 0'


def normalize(sql):
    # Probe SQLs contain no literals. Do not generalize this to real SQL semantics.
    return ' '.join(sql.strip().rstrip(';').split()) if isinstance(sql, str) else None


@dataclass
class Probe:
    name: str
    strategy: str
    question: str = QUESTION
    responses: list[str] = field(default_factory=lambda: [SQL_A])
    execution: dict = field(default_factory=dict)
    expected: str = SQL_A
    accepted: list[str] = field(default_factory=list)
    error: str = ''
    marker: str = ''
    error_class: str = ''
    steps: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)


class ProbeIO:
    """Independent spy on all solver requests and scripted execution results."""
    schema = SCHEMA

    def __init__(self, probe):
        self.probe = probe
        self.trace = []
        self.samples = 0
        self.answered_steps = set()

    def llm(self, prompt, system='', temperature=0., n=1):
        if not isinstance(prompt, str) or not isinstance(system, str):
            raise TypeError('solver prompt/system must be text')
        if type(n) is not int or n < 1:
            raise ValueError('invalid n')
        if self.samples+n > 12:
            raise RuntimeError('probe solver-call limit exceeded')
        p = self.probe
        attribution = {}
        # These scripts respond to content, not merely call position, for dataflow probes.
        if p.strategy in ('repair','error_classify') and self.samples > 0:
            response = p.expected if p.error and p.error in prompt+system else SQL_C
        elif p.strategy == 'schema_link' and self.samples > 0:
            response = p.expected if p.marker in prompt+system else SQL_C
        elif p.strategy == 'decompose' and self.samples > 0:
            if all(a in prompt+system for a in p.answers):
                response = p.expected
            else:
                mentioned = [i for i,step in enumerate(p.steps) if step in prompt+system]
                unseen = [i for i in mentioned if i not in self.answered_steps]
                candidates = unseen or mentioned
                # An earlier answered step can legitimately appear as context.
                # Multiple still-unanswered steps do not identify a unique target.
                index = candidates[0] if len(candidates) == 1 else None
                attribution = dict(decomposition_step=index,
                    decomposition_candidates=candidates,
                    decomposition_ambiguous=len(candidates) > 1)
                response = p.answers[index] if index is not None else 'UNRELATED'
                if index is not None:
                    self.answered_steps.add(index)
        else:
            response = None
        values = [response if response is not None else p.responses[min(self.samples+j,len(p.responses)-1)] for j in range(n)]
        self.samples += n
        result = values if n > 1 else values[0]
        self.trace.append(dict(kind='llm', prompt=prompt, system=system, n=n,
                               temperature=temperature, response=copy.deepcopy(result), **attribution))
        return result

    def execute(self, sql):
        result = self.probe.execution.get(normalize(sql), dict(ok=True, rows=[['A']], error=None))
        result = copy.deepcopy(result)
        self.trace.append(dict(kind='execute', sql=sql, **copy.deepcopy(result)))
        return result


def scenarios(strategy, salt='v3dev'):
    if strategy not in STRATEGIES:
        raise ValueError('unknown explicit strategy')
    def p(name, **kwargs):
        return Probe(name=name, strategy=strategy, **kwargs)
    if strategy in ('repair','error_classify'):
        probes = [p('success_no_repair', responses=[SQL_A,SQL_B], expected=SQL_A)]
        classes = ('syntax','schema','semantics') if strategy == 'error_classify' else ('syntax',)
        for category in classes:
            for label, answer in (('a',SQL_B), ('b',SQL_C)):
                error = f'{category} failure [{salt}_{category}_{label}]'
                probes.append(p(f'{category}_{label}', responses=[SQL_A], error=error,
                    error_class=category, expected=answer,
                    execution={SQL_A: dict(ok=False, rows=[], error=error)}))
        return probes
    if strategy == 'vote3':
        return [p('late_majority', responses=[SQL_A,SQL_B,SQL_B], expected=SQL_B,
                   execution={SQL_A:dict(ok=True,rows=[['A']],error=None),SQL_B:dict(ok=True,rows=[['B']],error=None)}),
                p('permuted_majority', responses=[SQL_B,SQL_B,SQL_A], expected=SQL_B,
                   execution={SQL_A:dict(ok=True,rows=[['A']],error=None),SQL_B:dict(ok=True,rows=[['B']],error=None)}),
                p('flipped_majority', responses=[SQL_B,SQL_A,SQL_A], expected=SQL_A,
                   execution={SQL_A:dict(ok=True,rows=[['A']],error=None),SQL_B:dict(ok=True,rows=[['B']],error=None)}),
                p('equivalent_results', responses=[SQL_A,SQL_B,SQL_C], expected=SQL_A,accepted=[SQL_C],
                   execution={SQL_A:dict(ok=True,rows=[['same']],error=None),SQL_B:dict(ok=True,rows=[['B']],error=None),SQL_C:dict(ok=True,rows=[['same']],error=None)}),
                p('execution_majority_flipped', responses=[SQL_A,SQL_B,SQL_C], expected=SQL_B,accepted=[SQL_C],
                   execution={SQL_A:dict(ok=True,rows=[['A']],error=None),SQL_B:dict(ok=True,rows=[['same']],error=None),SQL_C:dict(ok=True,rows=[['same']],error=None)}),
                p('execution_majority_AB', responses=[SQL_A,SQL_B,SQL_C], expected=SQL_A,accepted=[SQL_B],
                   execution={SQL_A:dict(ok=True,rows=[['same']],error=None),SQL_B:dict(ok=True,rows=[['same']],error=None),SQL_C:dict(ok=True,rows=[['C']],error=None)})]
    if strategy == 'two_view':
        return [p('first_empty', responses=[SQL_A,SQL_B], expected=SQL_B,
                    execution={SQL_A:dict(ok=True,rows=[],error=None),SQL_B:dict(ok=True,rows=[['B']],error=None)}),
                p('second_empty', responses=[SQL_A,SQL_B], expected=SQL_A,
                    execution={SQL_A:dict(ok=True,rows=[['A']],error=None),SQL_B:dict(ok=True,rows=[],error=None)}),
                p('both_nonempty', responses=[SQL_A,SQL_B], expected=SQL_A,
                    execution={SQL_A:dict(ok=True,rows=[['A']],error=None),SQL_B:dict(ok=True,rows=[['B']],error=None)}),
                p('first_failed', responses=[SQL_A,SQL_B], expected=SQL_B,
                    execution={SQL_A:dict(ok=False,rows=[],error='syntax'),SQL_B:dict(ok=True,rows=[['B']],error=None)})]
    if strategy == 'schema_link':
        return [p(f'link_{i}', marker=f'{salt}_link_{i}', expected=answer,
                  responses=[f'ledger(id) [{salt}_link_{i}]']) for i,answer in enumerate((SQL_A,SQL_B))]
    if strategy == 'decompose':
        probes=[]
        for i,answer in enumerate((SQL_A,SQL_B)):
            steps=[f'{salt}_part_{j}' for j in range(2)]
            answers=['PAYLOAD_'+hashlib.sha256(f'{salt}|payload|{i}|{j}'.encode()).hexdigest()[:16] for j in range(2)]
            probes.append(p(f'parts_{i}', responses=[json.dumps(steps)], steps=steps,answers=answers,expected=answer))
        return probes
    if strategy == 'hint_guard':
        return [p('no_hint'), *[p(f'hint_{i}', question=QUESTION+f'\nHint: id must exceed {value}.',
                  marker=f'id must exceed {value}.') for i,value in enumerate((317,941))]]
    return [p('format_original'), p('format_changed_question',question='Return ledger amounts.')]


def assess(probe, final, trace):
    calls = [x for x in trace if x['kind']=='llm']
    executions = [x for x in trace if x['kind']=='execute']
    def text(c):
        return c['system']+'\n'+c['prompt']
    reasons=[]
    if not calls:
        return ['no_solver_request']
    if normalize(final) not in [normalize(v) for v in [probe.expected]+probe.accepted]:
        reasons.append('counterfactual_output_mismatch')
    strategy=probe.strategy
    if strategy in ('hint_guard','format_guard'):
        if sum(c['n'] for c in calls) != 1:
            reasons.append('single_call_contract_not_met')
        request=text(calls[0])
        if probe.question not in request or SCHEMA not in request:
            reasons.append('original_question_or_schema_not_preserved')
        residual=request.replace(probe.question,'').replace(SCHEMA,'')
        if strategy=='hint_guard' and probe.marker:
            if probe.marker not in residual or not re.search(r'\b(must|required|requirement|constraint)\b',residual,re.I):
                reasons.append('explicit_hint_restatement_not_observed')
        if strategy=='format_guard':
            if '```sql' not in residual or not re.search(r'\b(only|no extra|nothing else)\b',residual,re.I):
                reasons.append('explicit_sql_only_fence_requirement_not_observed')
        # Literal witnesses cannot establish affirmative semantics or exclude
        # negation/paraphrase errors. Every prompt strategy requires an independent
        # semantic decision on the complete request before admission.
        reasons.append('semantic_prompt_review_required')
    elif strategy in ('repair','error_classify'):
        if not executions or normalize(executions[0]['sql']) != SQL_A:
            reasons.append('initial_sql_not_executed')
        if any(c['n'] != 1 for c in calls):
            reasons.append('extra_batched_samples')
        if not probe.error:
            if sum(c['n'] for c in calls) != 1:
                reasons.append('unconditional_extra_generation')
        else:
            failed_index=next((i for i,x in enumerate(trace) if x['kind']=='execute' and not x['ok']),len(trace))
            later=[x for x in trace[failed_index+1:] if x['kind']=='llm']
            if not any(probe.error in text(c) for c in later):
                reasons.append('execution_feedback_not_carried_forward')
            if strategy=='error_classify':
                classified=[c for c in later if set(re.findall(r'\b(syntax|schema|semantics)\b',
                    text(c).replace(probe.error,'').lower())) == {probe.error_class}]
                if not classified:
                    reasons.append('unambiguous_error_class_not_observed')
                reasons.append('classification_action_semantics_review_required')
    elif strategy in ('vote3','two_view'):
        need=3 if strategy=='vote3' else 2
        outputs=[v for c in calls for v in (c['response'] if isinstance(c['response'],list) else [c['response']])]
        if len(outputs)!=need:
            reasons.append('wrong_candidate_count')
        if any(not any(normalize(e['sql'])==normalize(sql) for e in executions) for sql in outputs):
            reasons.append('candidate_not_executed')
        if strategy=='two_view' and (len(calls)!=2 or normalize(text(calls[0]))==normalize(text(calls[1]))):
            reasons.append('distinct_formulation_requests_not_observed')
        if strategy=='two_view':
            reasons.append('formulation_semantics_review_required')
    elif strategy=='schema_link':
        if len(calls)<2 or not any(probe.marker in text(c) and 'ledger(id)' in text(c) and 'unused' not in text(c) for c in calls[1:]):
            reasons.append('linked_subset_not_carried_forward')
    elif strategy=='decompose':
        later=calls[1:]
        ambiguous = any(c.get('decomposition_ambiguous', False) for c in later)
        indices = [c.get('decomposition_step') for c in later[:-1]]
        known = [i for i in indices if i is not None]
        if (len(calls)<4 or known != sorted(set(known)) or
                (not ambiguous and indices != list(range(len(probe.steps))))):
            reasons.append('ordered_subquestions_not_answered')
        if not ambiguous and (not later or not all(answer in text(later[-1]) for answer in probe.answers)):
            reasons.append('partial_answers_not_assembled')
        if ambiguous:
            # A scripted response to an unassigned request cannot support an
            # output/assembly failure. Retain independent structural failures.
            reasons = [r for r in reasons if r != 'counterfactual_output_mismatch']
            reasons.append('decomposition_request_attribution_ambiguous')
    return reasons


def run_probe(solve: Callable, probe):
    io=ProbeIO(probe)
    try:
        final=solve(io,probe.question)
        if not isinstance(final,str) or not final.strip():
            raise TypeError('solve must return a nonempty SQL string')
        reasons=assess(probe,final,io.trace)
        # Wording/paraphrase uncertainty must not reproduce the old false "no mechanism" verdict.
        semantic={'semantic_prompt_review_required','formulation_semantics_review_required',
                  'classification_action_semantics_review_required',
                  'decomposition_request_attribution_ambiguous'}
        observational={'explicit_hint_restatement_not_observed','explicit_sql_only_fence_requirement_not_observed',
                       'original_question_or_schema_not_preserved',
                       'unambiguous_error_class_not_observed'}
        hard=[r for r in reasons if r not in semantic|observational]
        status='fail' if hard else ('review_required' if reasons else 'pass')
        return dict(probe=probe.name,status=status,reasons=reasons,final=final,trace=io.trace,error=None)
    except Exception as exc:
        return dict(probe=probe.name,status='execution_failure',reasons=[],final=None,trace=io.trace,
                    error=f'{type(exc).__name__}: {exc}')


def evaluate(solve, strategy, salt='v3dev'):
    probes=scenarios(strategy,salt)
    runs=[run_probe(solve,p) for p in probes]
    if strategy=='error_classify':
        templates={}
        for p,r in zip(probes,runs):
            if not p.error or r['status'] not in ('pass','review_required'):
                continue
            texts=[c['system']+'\n'+c['prompt'] for c in r['trace'] if c['kind']=='llm' and p.error in c['system']+c['prompt']]
            templates.setdefault(p.error_class,set()).update(' '.join(re.findall(r'\w+',re.sub(
                r'\b(syntax|schema|semantics)\b','CLASS',t.replace(p.error,'ERROR'),flags=re.I))) for t in texts)
        categories=list(templates)
        if any(templates[a]&templates[b] for i,a in enumerate(categories) for b in categories[i+1:]):
            # Shared text can be an intermediate classification request rather
            # than the repair action. Template equality is a review lead only.
            runs.append(dict(probe='cross_class_action',status='review_required',reasons=['same_action_template_across_error_classes'],final=None,trace=[],error=None))
    statuses={r['status'] for r in runs}
    verdict=next((s for s in ('execution_failure','fail','review_required') if s in statuses),'pass')
    return dict(strategy=strategy,verdict=verdict,scope='v3 exposed-control development; independent calibration and production adapter pending',runs=runs)
