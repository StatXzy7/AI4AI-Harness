"""Render planning distributions; this is not a manuscript experiment figure."""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from experiment.revision.replay import ROOT,digest

LABELS={'equal_probability_null':'Equal-probability null',
        'fixed_strength_no_interaction':'Fixed strengths, no interaction',
        'task_interaction':'Task-specific interaction',
        'shared_block_null':'Shared time shocks, null',
        'interaction_and_blocks':'Interaction + time shocks',
        'cache_coupled_null':'Code-keyed cache, null'}


def main():
    out=ROOT/'artifacts/revision_20260910'
    source=out/'repeat_planning.json'
    data=json.loads(source.read_text(encoding='utf-8'))
    if data['n_sim']!=1000:
        raise ValueError('final planning figure expects1000 draws per setting')
    rows=data['results']
    fig,(left,right)=plt.subplots(1,2,figsize=(13,5.3),gridspec_kw={'width_ratios':[1.5,1]})
    focus=[r for r in rows if (r['n_tasks'],r['n_repeats'])==(200,4)]
    for y,r in enumerate(focus):
        stat=r['real_minus_dev_fixed_clone']
        mean=np.array(stat['mean'])*100
        q=np.array(stat['planning_quantiles_025_975'])*100
        left.errorbar(mean[3],y-.12,xerr=[[mean[3]-q[0,3]],[q[1,3]-mean[3]]],
                      fmt='o',color='#287D8E',capsize=3,label='Observed repeat advantage' if y==0 else None)
        left.plot(mean[4],y,'s',color='#D48324',label='Fresh-probability fitted-policy value' if y==0 else None)
        left.plot(mean[0],y+.12,'D',color='#495A99',label='Available stable headroom' if y==0 else None)
    left.set_yticks(range(len(focus)),[LABELS[r['scenario']] for r in focus])
    left.invert_yaxis()
    left.set_ylim(len(focus)+.7,-.5)  # reserve a legend band below the last scenario
    left.axvline(0,color='gray',lw=.8)
    left.set_xlabel('Real minus dev-fixed clones (percentage points)')
    left.set_title('200 tasks, 4 repeats: different estimands')
    left.legend(loc='lower left',fontsize=8)
    designs=[(200,4),(400,4),(200,8),(400,8)]
    for name,offset,color in [('task_interaction',-.08,'#287D8E'),('interaction_and_blocks',.08,'#D48324')]:
        for i,design in enumerate(designs):
            row=next(r for r in rows if r['scenario']==name and (r['n_tasks'],r['n_repeats'])==design)
            stat=row['real_minus_dev_fixed_clone']
            mean=100*stat['mean'][3]
            lo,hi=100*np.array(stat['planning_quantiles_025_975'])[:,3]
            right.errorbar(i+offset,mean,yerr=[[mean-lo],[hi-mean]],fmt='o',color=color,capsize=3,
                           label=LABELS[name] if i==0 else None)
    right.axhline(0,color='gray',lw=.8)
    right.axhline(1,color='gray',ls='--',lw=.8,label='1 pp planning reference (not frozen)')
    right.set_xticks(range(4),[f'{n} tasks\n{r} repeats' for n,r in designs])
    right.set_ylabel('Observed repeat-advantage contrast (pp)')
    right.set_title('More repetitions change what can be learned')
    right.legend(fontsize=8,loc='lower right')
    fig.suptitle('Design simulation only — not experimental results',fontsize=14)
    fig.text(.5,.01,'Bars: 2.5–97.5% of 1,000 simulated datasets; not confidence intervals. Four cells; three equal-size groups; costs are not matched.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.06,1,.94])
    fig.savefig(out/'repeat_planning.png',dpi=160)
    fig.savefig(out/'repeat_planning.pdf')
    plt.close(fig)
    report=json.dumps({'input_sha256':digest(source),'renderer_sha256':digest(ROOT/'experiment/revision/render_planning.py'),
        'outputs':{name:digest(out/name) for name in ('repeat_planning.png','repeat_planning.pdf')}},indent=2)+'\n'
    (out/'repeat_planning_assets.json').write_text(report,encoding='utf-8')


if __name__=='__main__':
    main()
