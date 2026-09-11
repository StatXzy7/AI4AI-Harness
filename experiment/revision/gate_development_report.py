"""Generate the development control report; no scientific calibration claim."""
import json
import inspect
import hashlib
import re
from pathlib import Path

from experiment.revision import gate_controls as controls
from experiment.revision.gate_runtime_adapter import candidate
from experiment.revision.gate_v2 import SCHEMA, STRATEGIES, evaluate, scenarios
from experiment.revision.replay import ROOT, digest


def main():
    cases=[]
    for label,collection in [('positive',controls.POSITIVE),('negative',controls.NEGATIVE)]:
        for strategy,solve in collection.items():
            cases.append(dict(name=solve.__name__,label=label,**evaluate(solve,strategy)))
    for name,(strategy,solve) in controls.ADVERSARIAL.items():
        cases.append(dict(name=name,label='adversarial_negative',**evaluate(solve,strategy)))
    for name,solve in [('crash',controls.crash),('invalid',controls.invalid)]:
        cases.append(dict(name=name,label='execution_failure',**evaluate(solve,'repair')))
    runtime=[]
    sources=[]
    for name,strategy in [('hpc_repair','repair'),('hpc_vote3','vote3'),
                          ('neg_uncond_twocall','repair'),('neg_selectfirst','vote3'),('bare','format_guard')]:
        path=ROOT/f'external/TTHE/text_to_sql/agents/{name}.py'
        sources.append(path)
        with candidate(path) as solve:
            runtime.append(dict(name=name,**evaluate(solve,strategy)))
    summary={strategy:{label:{status:sum(r['strategy']==strategy and r['label']==label and r['verdict']==status for r in cases)
                             for status in ('pass','fail','review_required','execution_failure')}
                         for label in ('positive','negative','adversarial_negative','execution_failure')}
             for strategy in STRATEGIES}
    inputs=sources+[ROOT/f'experiment/revision/{name}.py' for name in (
        'gate_v2','gate_controls','gate_runtime_adapter','test_gate_v2','test_gate_runtime_adapter','replay')]+[
        Path(__file__),ROOT/'external/TTHE/text_to_sql/harness_base.py',
        ROOT/'external/TTHE/text_to_sql/resultkey.py',ROOT/'external/TTHE/ase/llm.py',
        ROOT/'review-stage/GATE_V2_CONTRACTS.md']
    report=dict(version='gate-v2-development-20260910-v1',release_verdict='not ready',
        scope='same-author development controls plus adversarial regression mutants and trusted local runtime adapter; no independent calibration, no benchmark collection',
        admission='probe pass is a structural observation, not production admission; four semantic families require independent adjudication and all strategies require held-out calibration',
        outstanding=['independent calibration fixtures and cross-model adjudication','frozen semantic decisions for hint/format/two_view/error_classify',
                     'broader robustness of prompt/dataflow/branch contracts','common raw pool and fixed budget','full runtime restoration and prospective freeze'],
        development_outcome_counts=summary,cases=cases,trusted_runtime=runtime,
        inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p)) for p in inputs])
    out=ROOT/'artifacts/revision_20260910/gate_v2_development.json'
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    # A separate packet omits expected labels and current verdicts. Do not send
    # the labeled development report as though it were blinded calibration data.
    packet=[]
    functions={f.__name__:f for f in [*controls.POSITIVE.values(),*controls.NEGATIVE.values(),
                                    *(f for _,f in controls.ADVERSARIAL.values())]}
    for case in cases:
        if case['strategy'] not in ('hint_guard','format_guard','two_view','error_classify'):
            continue
        source=inspect.getsource(functions[case['name']])
        source_hash=hashlib.sha256(source.encode('utf-8')).hexdigest()
        displayed_source=re.sub(r'def \w+\(', 'def candidate(', source, count=1)
        probes={p.name:p for p in scenarios(case['strategy'])}
        runs=[dict(probe=r['probe'],question=probes[r['probe']].question,
                   trace=r['trace'],final=r['final']) for r in case['runs'] if r['probe'] in probes]
        packet.append(dict(case_id=hashlib.sha256((case['strategy']+source_hash).encode()).hexdigest()[:16],
            strategy=case['strategy'],original_callable_source_sha256=source_hash,
            source=displayed_source,displayed_source_sha256=hashlib.sha256(displayed_source.encode('utf-8')).hexdigest(),
            schema=SCHEMA,runs=runs,runs_sha256=hashlib.sha256(json.dumps(runs,sort_keys=True,
                ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()))
    packet_out=out.with_name('gate_v2_semantic_review_packet.json')
    packet_out.write_text(json.dumps(dict(version=report['version'],
        status='awaiting independent semantic adjudication; development cases, not held-out calibration',
        rubric='review-stage/GATE_V2_CONTRACTS.md section 3',contract_sha256=digest(ROOT/'review-stage/GATE_V2_CONTRACTS.md'),
        cases=packet),indent=2)+'\n',encoding='utf-8')
    print('Development cases:',len(cases),'trusted runtime:',len(runtime))
    print({label:{s:sum(r['label']==label and r['verdict']==s for r in cases) for s in ('pass','fail','review_required','execution_failure')}
          for label in ('positive','negative','adversarial_negative','execution_failure')})
    print('Release verdict:',report['release_verdict'])


if __name__ == '__main__':
    main()
