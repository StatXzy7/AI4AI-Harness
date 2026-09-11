"""Identification checks and conservative finite-pool stable-headroom bounds.

No formal execution-independence or sample-size approval is supplied here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from experiment.revision.replay import ROOT, digest
from experiment.revision.repeat_planning import stable_headroom, tied_max_weights


def freeze_choices(discovery):
    """Input cell,group,repeat,member,task; freeze uniform tie policies."""
    scores = np.asarray(discovery).mean(axis=2)
    return tied_max_weights(scores, 2), tied_max_weights(scores.mean(axis=3), 2)


def validation_differences(policy, validation):
    """Per independent block differences against EVERY fixed member.

    policy[cell,group,member,task] must be frozen before validation is seen.
    Output cell,group,block,member. Averaging tasks retains whole-block dependence.
    """
    selected = np.einsum('cght,cgrht->cgrt', policy, validation).mean(axis=-1)
    return selected[..., None] - validation.mean(axis=-1)


def policy_witness(probabilities, policy):
    """Known-probability witness <= stable headroom, possibly negative.

    Last axes member,task. A negative witness is not negative stable headroom.
    """
    selected = (probabilities*policy).sum(axis=-2).mean(axis=-1)
    return selected-probabilities.mean(axis=-1).max(axis=-1)


def stable_bounds(lower, upper):
    """Propagate simultaneous probability bands; any dependence across entries.

    Returned last axis is lower,upper. Bounds concern a fixed task/code pool.
    They do not certify that supplied bands have statistical coverage.
    """
    lower, upper = np.asarray(lower), np.asarray(upper)
    if lower.shape != upper.shape or lower.ndim < 2:
        raise ValueError('matching arrays with member,task axes required')
    if not (np.isfinite(lower).all() and np.isfinite(upper).all()
            and (lower >= 0).all() and (upper <= 1).all() and (lower <= upper).all()):
        raise ValueError('valid probability bands required')
    lo = np.maximum(0., lower.max(axis=-2).mean(axis=-1)-upper.mean(axis=-1).max(axis=-1))
    # With K members, oracle - best-fixed cannot exceed 1 - 1/K.
    hi = np.minimum(1-1/lower.shape[-2], upper.max(axis=-2).mean(axis=-1)-lower.mean(axis=-1).max(axis=-1))
    return np.stack([lo, np.maximum(0., hi)], axis=-1)


def contrast_bounds(bounds, real=0, clone=2):
    """cell,group,bound -> paired-cell-average contrast interval.

    Lower bound minus lower bound is NOT a lower bound for their difference.
    Simultaneous coverage across cells/groups is required before this operation.
    """
    return np.array([(bounds[:,real,0]-bounds[:,clone,1]).mean(),
                     (bounds[:,real,1]-bounds[:,clone,0]).mean()])


def hoeffding_bands(validation, alpha=.05):
    """Conservative simultaneous bands conditional on fixed tasks/codes.

    Requires independent, identically distributed validation BLOCKS over time;
    arbitrary dependence within a block is allowed. This code cannot verify
    provider stationarity or independent cache-free execution. Blocks are axis2.
    It is a conservative benchmark, not the proposed formal primary estimator.
    """
    validation = np.asarray(validation)
    if validation.ndim != 5 or validation.shape[2] < 1 or not 0 < alpha < 1:
        raise ValueError('nonempty cell,group,block,member,task data and 0<alpha<1 required')
    if not np.isin(validation, [0,1]).all():
        raise ValueError('binary outcomes required')
    means = validation.mean(axis=2)
    radius = float(np.sqrt(np.log(2*means.size/alpha)/(2*validation.shape[2])))
    return np.maximum(0., means-radius), np.minimum(1., means+radius), radius


def counterexamples():
    # The discovery-selected fixed member is bare, despite a truly stronger
    # constant-accuracy member. The event has positive probability under p.
    p = np.array([[.2,.2],[.8,.8],[.5,.5]])
    discovery = np.array([[1.,1.],[1.,0.],[0.,1.]])[None,None,None]
    policy, fixed = freeze_choices(discovery)
    selected = float((p*policy[0,0]).sum(axis=0).mean())
    baseline = float((p.mean(axis=1)*fixed[0,0]).sum())
    # Mixed bare+same-code clones can have real stable complementarity.
    clone_p = np.array([[.9,.1],[.1,.9],[.1,.9]])
    wrong_discovery = np.array([[0.,1.],[1.,0.],[1.,0.]])[None,None,None]
    wrong_policy, _ = freeze_choices(wrong_discovery)
    real_p = np.full((3,2), .5)
    real_policy = np.full((3,2), 1/3)
    witnesses = [float(policy_witness(real_p, real_policy)),
                 float(policy_witness(clone_p, wrong_policy[0,0]))]
    stable = [float(stable_headroom(real_p)), float(stable_headroom(clone_p))]
    return dict(discovery_fixed_trap=dict(probabilities=p.tolist(), discovery=discovery[0,0,0].tolist(),
        frozen_policy=policy[0,0].tolist(), selected_accuracy=selected,
        discovery_selected_fixed_accuracy=baseline, apparent_advantage=selected-baseline,
        best_fixed_accuracy=float(p.mean(axis=1).max()), stable_headroom=float(stable_headroom(p)),
        all_fixed_witness=float(policy_witness(p,policy[0,0]))),
        difference_of_lower_bounds_trap=dict(real_probabilities=real_p.tolist(), clone_probabilities=clone_p.tolist(),
        real_witness=witnesses[0], clone_witness=witnesses[1], invalid_witness_difference=witnesses[0]-witnesses[1],
        real_stable_headroom=stable[0], clone_stable_headroom=stable[1], true_stable_difference=stable[0]-stable[1]))


def main():
    out = ROOT/'artifacts/revision_20260910'
    parameter_count = 4*3*3*180
    report = dict(version='stable-identification-checks-v1',
        scope='exact constructed examples and conservative bound arithmetic; no empirical experiment or inference clearance',
        counterexamples=counterexamples(),
        band_radius_arithmetic=[dict(validation_blocks=r, simultaneous_parameters=parameter_count,
            alpha=.05, hoeffding_radius=float(np.sqrt(np.log(2*parameter_count/.05)/(2*r))))
            for r in [4,8,16,64,256,1024]],
        limitations=['fresh heldout gain against a discovery-selected fixed comparator does not identify stable headroom',
            'a validated policy compared against every fixed member witnesses a lower bound, not equality with stable headroom',
            'subtracting two lower bounds does not bound a difference; use L_real-U_clone and U_real-L_clone',
            'a dev-code clone pool retaining distinct bare can have positive stable headroom',
            'Hoeffding bands require stationary independent temporal blocks; no cross-task/cell independence needed',
            'generic probability bands do not exploit equality of clone source probabilities and can be extremely wide',
            'fixed-pool bounds do not generalize to new databases/builders, prove mechanism causality or match compute'],
        inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p)) for p in
            [Path(__file__),ROOT/'experiment/revision/repeat_planning.py',ROOT/'experiment/revision/replay.py']])
    (out/'stable_identification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report['counterexamples'],indent=2))


if __name__ == '__main__':
    main()
