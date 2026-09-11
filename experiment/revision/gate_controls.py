"""Hand-written DEVELOPMENT controls; same-author, not independent calibration."""
import json
from collections import Counter


def repair(io, question):
    sql=io.llm(io.schema+'\n'+question)
    for _ in range(2):
        outcome=io.execute(sql)
        if outcome['ok']:
            return sql
        sql=io.llm(io.schema+'\n'+question+'\nPrevious SQL: '+sql+'\nError: '+outcome['error'])
    return sql


def error_classify(io, question):
    sql=io.llm(io.schema+'\n'+question)
    for _ in range(2):
        outcome=io.execute(sql)
        if outcome['ok']:
            return sql
        error=outcome['error']
        category=next((c for c in ('syntax','schema','semantics') if c in error.lower()),'unknown')
        actions={'syntax':'correct grammar','schema':'correct table and column references','semantics':'correct the query logic'}
        sql=io.llm(io.schema+'\n'+question+f'\n{category}-specific fix: {actions[category]}\n'+error)
    return sql


def vote3(io, question):
    candidates=io.llm(io.schema+'\n'+question,n=3,temperature=.7)
    outcomes=[io.execute(sql) for sql in candidates]
    counts=Counter(json.dumps(r['rows'],sort_keys=True) for r in outcomes if r['ok'])
    best=max(counts,key=counts.get)
    return next(sql for sql,r in zip(candidates,outcomes) if r['ok'] and json.dumps(r['rows'],sort_keys=True)==best)


def two_view(io, question):
    candidates=[io.llm(io.schema+'\n'+question+'\nUse a join formulation.'),
                io.llm(io.schema+'\n'+question+'\nUse a subquery formulation.')]
    outcomes=[io.execute(sql) for sql in candidates]
    return next((sql for sql,r in zip(candidates,outcomes) if r['ok'] and r['rows']),candidates[0])


def schema_link(io, question):
    linked=io.llm(io.schema+'\n'+question+'\nIdentify the relevant tables and columns.')
    return io.llm(question+'\nWrite SQL against only the linked subset:\n'+linked)


def decompose(io, question):
    plan=json.loads(io.llm(io.schema+'\n'+question+'\nReturn ordered subquestions as a JSON array.'))
    partial=[io.llm(io.schema+'\nAnswer subquestion: '+step) for step in plan]
    return io.llm(io.schema+'\n'+question+'\nAssemble final SQL from:\n'+'\n'.join(partial))


def hint_guard(io, question):
    hint=question.partition('Hint:')[2].strip()
    extra='\nHard requirement: '+hint if hint else ''
    return io.llm(io.schema+'\n'+question+extra)


def format_guard(io, question):
    return io.llm(io.schema+'\n'+question+'\nUse only schema-defined names. Return only a ```sql fence, no extra text.')


def passthrough(io, question):
    return io.llm(io.schema+'\n'+question)


def unconditional(io, question):
    first=io.llm(io.schema+'\n'+question)
    outcome=io.execute(first)
    return io.llm(io.schema+'\n'+question+'\n'+str(outcome['error']))


def read_discard(io, question):
    first=io.llm(io.schema+'\n'+question)
    outcome=io.execute(first)
    if outcome['ok']:
        return first
    _=outcome['error']
    return io.llm(io.schema+'\n'+question+'\nTry again.')


def select_first(io, question):
    candidates=io.llm(io.schema+'\n'+question,n=3,temperature=.7)
    for sql in candidates:
        io.execute(sql)
    return candidates[0]


def two_view_ignore_rows(io, question):
    first=io.llm(io.schema+'\n'+question+'\nJoin formulation.')
    second=io.llm(io.schema+'\n'+question+'\nSubquery formulation.')
    io.execute(first)
    io.execute(second)
    return first


def schema_discard(io, question):
    io.llm(io.schema+'\n'+question+'\nFind tables.')
    return io.llm(io.schema+'\n'+question)


def decompose_discard(io, question):
    plan=json.loads(io.llm(io.schema+'\n'+question+'\nPlan.'))
    for step in plan:
        io.llm(step)
    return io.llm(io.schema+'\n'+question)


def crash(io, question):
    raise RuntimeError('intentional development control failure')


def invalid(io, question):
    io.llm(question)
    return ['not a SQL string']


POSITIVE={name:globals()[name] for name in ('repair','vote3','schema_link','hint_guard',
                                          'two_view','decompose','error_classify','format_guard')}
NEGATIVE={'repair':read_discard,'vote3':select_first,'schema_link':schema_discard,
          'hint_guard':passthrough,'two_view':two_view_ignore_rows,'decompose':decompose_discard,
          'error_classify':repair,'format_guard':passthrough}

# Adversarial mutants discovered by the two review axes (no benchmark outcomes).
def string_vote(io, question):
    candidates=io.llm(io.schema+'\n'+question,n=3,temperature=.7)
    for sql in candidates:
        io.execute(sql)
    return Counter(candidates).most_common(1)[0][0]


def all_classes(io, question):
    first=io.llm(io.schema+'\n'+question)
    outcome=io.execute(first)
    if outcome['ok']:
        return first
    return io.llm('syntax schema semantics\n'+outcome['error'])


def batch_repair(io, question):
    first=io.llm(io.schema+'\n'+question,n=2)[0]
    outcome=io.execute(first)
    if outcome['ok']:
        return first
    return io.llm(outcome['error'])


def whitespace_views(io, question):
    request=io.schema+'\n'+question
    candidates=[io.llm(request),io.llm(request+' ')]
    outcomes=[io.execute(sql) for sql in candidates]
    return next((sql for sql,r in zip(candidates,outcomes) if r['ok'] and r['rows']),candidates[0])


def negated_hint(io, question):
    return io.llm(io.schema+'\n'+question+'\nIgnore this requirement: '+question.partition('Hint:')[2].strip())


def negated_format(io, question):
    return io.llm(io.schema+'\n'+question+'\nDo NOT return only a ```sql fence; include explanatory prose.')


ADVERSARIAL={'string_vote':('vote3',string_vote),'all_classes':('error_classify',all_classes),
             'batch_repair':('repair',batch_repair),'whitespace_views':('two_view',whitespace_views),
             'negated_hint':('hint_guard',negated_hint),'negated_format':('format_guard',negated_format)}

# Second adversarial round: related but distinct errors were not covered initially.
def last_tie_string_vote(io, question):
    candidates=io.llm(io.schema+'\n'+question,n=3,temperature=.7)
    for sql in candidates:
        io.execute(sql)
    counts=Counter(candidates)
    return max(reversed(candidates),key=counts.get)


def punctuation_classes(io, question):
    first=io.llm(io.schema+'\n'+question)
    outcome=io.execute(first)
    if outcome['ok']:
        return first
    error=outcome['error']
    category=next(c for c in ('syntax','schema','semantics') if c in error)
    punctuation={'syntax':'!','schema':'?','semantics':'.'}[category]
    return io.llm(category+punctuation+' Try again.\n'+error)


def shared_two_actions(io, question):
    first=io.llm(io.schema+'\n'+question)
    outcome=io.execute(first)
    if outcome['ok']:
        return first
    error=outcome['error']
    category=next(c for c in ('syntax','schema','semantics') if c in error)
    action='correct query logic' if category=='semantics' else 'correct grammar'
    return io.llm(category+' '+action+'\n'+error)


def fabricated_parts(io, question):
    plan=json.loads(io.llm(io.schema+'\n'+question))
    for step in plan:
        io.llm(step)
    answers=[step.replace('_part_','_answer_') for step in plan]
    return io.llm(io.schema+'\n'+question+'\n'+'\n'.join(answers))


ADVERSARIAL.update({'last_tie_string_vote':('vote3',last_tie_string_vote),
    'punctuation_classes':('error_classify',punctuation_classes),
    'shared_two_actions':('error_classify',shared_two_actions),
    'fabricated_parts':('decompose',fabricated_parts)})
