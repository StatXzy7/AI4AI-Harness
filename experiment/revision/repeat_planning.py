"""API-free Monte Carlo planning for paired real/clone repeat experiments.

Planning distributions are not confidence intervals for the archived experiment.
No power/coverage claim or sample-size freeze is made by this simulator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from experiment.revision.replay import ROOT, digest

GROUPS=['real','bare_clone','dev_fixed_clone']
SCENARIOS={
    'equal_probability_null':dict(strength=0.,interaction=0.,block_sd=0.,cache=0.),
    'fixed_strength_no_interaction':dict(strength=.8,interaction=0.,block_sd=0.,cache=0.),
    'task_interaction':dict(strength=0.,interaction=.8,block_sd=0.,cache=0.),
    'shared_block_null':dict(strength=0.,interaction=0.,block_sd=1.2,cache=0.),
    'interaction_and_blocks':dict(strength=0.,interaction=.8,block_sd=1.2,cache=0.),
    'cache_coupled_null':dict(strength=0.,interaction=0.,block_sd=0.,cache=.9),
}


def logits(p):
    p=np.clip(p,1e-12,1-1e-12)
    return np.log(p)-np.log1p(-p)


def sigmoid(x):
    return 1/(1+np.exp(-x))


def stable_headroom(probabilities):
    """Last axes are member,task. Values are probabilities, not single executions."""
    return probabilities.max(axis=-2).mean(axis=-1)-probabilities.mean(axis=-1).max(axis=-1)


def tied_max_weights(values,axis):
    best=values.max(axis=axis,keepdims=True)
    ties=np.isclose(values,best,rtol=0,atol=1e-12)
    return ties/ties.sum(axis=axis,keepdims=True)


def fitted_policy_score(discovery,validation):
    """Mean over repetitions first; tie averaging is a uniform randomized policy.

    Inputs: cell,group,repeat,member,task. Fitting never sees validation outcomes.
    Returns cell,group retained advantage, selected accuracy, dev-fixed accuracy.
    """
    train=discovery.mean(axis=2)
    test=validation.mean(axis=2)
    per_task=tied_max_weights(train,axis=2)
    fixed=tied_max_weights(train.mean(axis=3),axis=2)
    chosen=(per_task*test).sum(axis=2).mean(axis=2)
    fixed_score=(fixed*test.mean(axis=3)).sum(axis=2)
    return np.stack([chosen-fixed_score,chosen,fixed_score],axis=-1)


def cross_repeat(outcomes,probabilities):
    """Two prespecified complementary half-splits; no repeated record crosses a split.

    Oracle score uses the known validation probabilities for the *fitted* policy,
    separately in each orientation; it is not the available stable headroom.
    """
    r=outcomes.shape[2]
    if r<2 or r%2:
        raise ValueError('an even repeat count >=2 is required')
    half=r//2
    observed=(fitted_policy_score(outcomes[:,:,:half],outcomes[:,:,half:])+
              fitted_policy_score(outcomes[:,:,half:],outcomes[:,:,:half]))/2
    oracle=(fitted_policy_score(outcomes[:,:,:half],probabilities[:,:,half:])+
            fitted_policy_score(outcomes[:,:,half:],probabilities[:,:,:half]))/2
    return observed,oracle


def real_probabilities(base,assignments,settings,n_cells):
    n=len(base)
    offsets=np.zeros((n_cells,3,n))
    offsets[:,1,:]=-settings['strength']
    offsets[:,2,:]=settings['strength']
    for cell in range(n_cells):
        sign=np.where(assignments[cell]==0,1.,-1.)
        offsets[cell,1,:]+=settings['interaction']*sign
        offsets[cell,2,:]-=settings['interaction']*sign
    return sigmoid(logits(base)[None,None,:]+offsets)


def build_populations(rng,n_tasks,n_cells,settings,mean_accuracy,concentration,n_dev=200):
    base=rng.beta(mean_accuracy*concentration,(1-mean_accuracy)*concentration,n_tasks)
    p=real_probabilities(base,rng.integers(0,2,size=(n_cells,n_tasks)),settings,n_cells)
    dev_base=rng.beta(mean_accuracy*concentration,(1-mean_accuracy)*concentration,n_dev)
    dev_p=real_probabilities(dev_base,rng.integers(0,2,size=(n_cells,n_dev)),settings,n_cells)
    dev=rng.random(dev_p.shape)<dev_p
    # One independent development acquisition, canonical first-index ties.
    chosen=dev.mean(axis=-1).argmax(axis=1)
    populations=np.empty((n_cells,3,3,n_tasks))
    populations[:,0]=p
    populations[:,1]=p[:,0:1]
    populations[:,2,0]=p[:,0]
    for c,h in enumerate(chosen):
        populations[c,2,1:]=p[c,h]
    # Code identity, unlike member identity, is shared among clones and bare.
    code_ids=np.zeros((n_cells,3,3),dtype=int)
    code_ids[:,0]=[0,1,2]
    for c,h in enumerate(chosen):
        code_ids[c,2]=[0,h,h]
    return populations,code_ids


def generate_execution(rng,p,code_ids,n_repeats,block_sd,cache):
    """Common time-block shock, independent draws unless code-keyed cache is active."""
    cells,groups,members,tasks=p.shape
    shifts=rng.normal(0,block_sd,n_repeats)
    probabilities=sigmoid(logits(p)[:,:,None,:,:]+shifts[None,None,:,None,None])
    outcomes=(rng.random(probabilities.shape)<probabilities).astype(float)
    if cache:
        cached=(rng.random((cells,3,tasks))<p[:,0]).astype(float)
        # Bare is the same code/request across all cells; non-bare code identity
        # is cell-specific. Clone members map to that same cached source draw.
        cached[:,0]=cached[0,0]
        for c in range(cells):
            for g in range(groups):
                for h in range(members):
                    use=rng.random((n_repeats,tasks))<cache
                    outcomes[c,g,:,h,:]=np.where(use,cached[c,code_ids[c,g,h]],outcomes[c,g,:,h,:])
    # With cache, these are the *fresh independent execution* probabilities.
    # Discrepancy from oracle evaluation exposes discovery/validation coupling.
    return outcomes,probabilities


def marginal_probabilities(p,block_sd):
    if not block_sd:
        return p
    nodes,weights=np.polynomial.hermite.hermgauss(24)
    return sum(w*sigmoid(logits(p)+np.sqrt(2)*block_sd*x) for x,w in zip(nodes,weights))/np.sqrt(np.pi)


def one_simulation(rng,n_tasks,n_repeats,settings,mean_accuracy,concentration,n_cells=4):
    p,codes=build_populations(rng,n_tasks,n_cells,settings,mean_accuracy,concentration)
    outcomes,probabilities=generate_execution(rng,p,codes,n_repeats,settings['block_sd'],settings['cache'])
    observed,oracle=cross_repeat(outcomes,probabilities)
    stable=stable_headroom(marginal_probabilities(p,settings['block_sd']))
    plugin=stable_headroom(outcomes.mean(axis=2))
    single=stable_headroom(outcomes).mean(axis=2)
    # All outputs average cells equally. Pool membership always includes bare.
    return np.stack([stable.mean(axis=0),single.mean(axis=0),plugin.mean(axis=0),
                     observed[:,:,0].mean(axis=0),oracle[:,:,0].mean(axis=0),
                     observed[:,:,1].mean(axis=0),observed[:,:,2].mean(axis=0)],axis=-1)


def summarize(values):
    return dict(mean=np.mean(values,axis=0).tolist(),
        monte_carlo_se=(np.std(values,axis=0,ddof=1)/np.sqrt(len(values))).tolist(),
        planning_quantiles_025_975=np.quantile(values,[.025,.975],axis=0).tolist())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--n-sim',type=int,default=1000)
    ap.add_argument('--seed',type=int,default=20260910)
    args=ap.parse_args()
    if args.n_sim<100:
        ap.error('at least100 simulations per scenario/design')
    out=ROOT/'artifacts/revision_20260910'
    sensitivity=json.loads((out/'sensitivity.json').read_text(encoding='utf-8'))
    flip=sensitivity['r2']['micro_verdict_flips']['rate']
    mean_accuracy=.64
    concentration=flip/(2*mean_accuracy*(1-mean_accuracy)-flip)
    rng=np.random.default_rng(args.seed)
    designs=[(200,4),(400,4),(200,8),(400,8)]
    results=[]
    for name,settings in SCENARIOS.items():
        for n_tasks,n_repeats in designs:
            values=np.array([one_simulation(rng,n_tasks,n_repeats,settings,mean_accuracy,concentration)
                             for _ in range(args.n_sim)])
            contrast=values[:,0]-values[:,2]
            contrast_bare=values[:,0]-values[:,1]
            row=dict(scenario=name,settings=settings,n_tasks=n_tasks,n_repeats=n_repeats,
                n_cells=4,n_groups=3,n_members_including_bare=3,
                evaluation_invocations=4*n_tasks*n_repeats*3*3,
                development_invocations=4*200*3,
                groups=summarize(values),real_minus_dev_fixed_clone=summarize(contrast),
                real_minus_bare_clone=summarize(contrast_bare),
                observed_minus_oracle_fitted=summarize(contrast[:,3]-contrast[:,4]),
                apparent_retained_over_1pp=float(np.mean(contrast[:,3]>.01)))
            results.append(row)
            print(name,n_tasks,n_repeats,'retained pp',round(100*contrast[:,3].mean(),3),
                  'oracle fitted pp',round(100*contrast[:,4].mean(),3),flush=True)
    report=dict(version='repeat-planning-20260910-v1',n_sim=args.n_sim,seed=args.seed,
        purpose='design sensitivity simulation; not observed study results, not power/CI coverage, not a sample-size freeze',
        group_order=GROUPS,metric_order=['available_stable_headroom','one_run_observed_headroom',
        'repeat_plugin_headroom','cross_repeat_advantage','oracle_fitted_policy_advantage',
        'cross_repeat_selected_accuracy','cross_repeat_dev_fixed_accuracy'],
        calibration=dict(mean_accuracy_assumption=mean_accuracy,flip_input=flip,beta_concentration=concentration,
            equation='flip = 2*mu*(1-mu)*kappa/(1+kappa) under iid Bernoulli draws from per-task Beta probabilities',
            limitation='illustrative moment match; R2 mixed cached/off acquisitions are not proof of iid noise or beta task probabilities'),
        scopes=['fixed4 independent population cells sharing task difficulty; not six-builder inference',
          'one200-task independent development acquisition selects clone code; development compute reported separately',
          'two complementary repeat halves, uniform tie averaging; validation records are never used for their own directional selection',
          'known fitted-policy probability score differs from available stable headroom; finite repeats can miss real complementarity',
          '24-node Gaussian quadrature defines marginal probabilities under shared block shifts',
          'cache stress shares bare across all cells and uses cell-specific non-bare code keys; intentionally violates independent-execution assumption',
          'quantiles are Monte Carlo planning distributions across simulated task sets/executions, not estimated95percent CIs',
          'no false-positive or coverage guarantee; formal inference and database clustering simulation remain outstanding',
          'equal member counts are not equal solver/token costs'],results=results,
        inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p)) for p in
            (Path(__file__),ROOT/'experiment/revision/replay.py',out/'sensitivity.json')])
    (out/'repeat_planning.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
