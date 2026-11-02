"""Reproducible, paired commercial sensitivity. No calibrated weather claims.

V1 varies only a declared additional downstream handling delay. It never
perturbs hourly weather, sailing geometry, fuel consumption or safety gates.
"""
from __future__ import annotations
import math
import random
from decimal import Decimal
from statistics import fmean,stdev
from typing import Literal
from pydantic import Field, model_validator
from .commercial import Strict, CommercialContext, evaluate, digest

VERSION='commercial-mc-shadow-v1'
SAMPLER='python-random-MT19937-discrete-cdf-triangular-v1'


class DelayDistribution(Strict):
    input: Literal['ADDITIONAL_DOWNSTREAM_HANDLING_DELAY'] = 'ADDITIONAL_DOWNSTREAM_HANDLING_DELAY'
    unit: Literal['hour'] = 'hour'
    kind: Literal['DISCRETE','TRIANGULAR']
    values: list[float] = Field(default_factory=list,max_length=32)
    weights: list[float] = Field(default_factory=list,max_length=32)
    minimum: float | None = Field(default=None,ge=0,le=720)
    mode: float | None = Field(default=None,ge=0,le=720)
    maximum: float | None = Field(default=None,ge=0,le=720)
    declaration: str = Field(min_length=8,max_length=500)
    dependency: Literal['ONE_SHARED_DELAY_FOR_ALL_CANDIDATES_AND_SHIPMENTS'] = 'ONE_SHARED_DELAY_FOR_ALL_CANDIDATES_AND_SHIPMENTS'

    @model_validator(mode='after')
    def valid_distribution(self):
        if self.kind=='DISCRETE':
            if not self.values or len(self.values)!=len(self.weights) or any(not math.isfinite(x) or not 0<=x<=720 for x in self.values) or any(not math.isfinite(w) or w<=0 for w in self.weights) or abs(sum(self.weights)-1)>1e-9:
                raise ValueError('Discrete hours and positive declared weights summing to one are required')
        elif self.minimum is None or self.mode is None or self.maximum is None or not self.minimum<=self.mode<=self.maximum:
            raise ValueError('Triangular minimum ≤ mode ≤ maximum is required')
        return self


class Simulation(Strict):
    mode: Literal['ASSUMPTION_SENSITIVITY','EMPIRICAL_SHADOW']
    seed: int = Field(ge=0,le=2**53-1)
    draws: int = Field(default=256,ge=16,le=4096)
    alpha: float = Field(default=.95,ge=.5,lt=1)
    tailPreference: float = Field(default=0,ge=0,le=1)
    distribution: DelayDistribution | None = None
    acknowledgedAssumptions: bool = False

    @model_validator(mode='after')
    def assumptions(self):
        if self.mode=='ASSUMPTION_SENSITIVITY' and (not self.distribution or not self.acknowledgedAssumptions): raise ValueError('Explicit distribution and deliberate assumption acknowledgement required')
        return self


def draw_world(config):
    rng=random.Random(config.seed);d=config.distribution;values=[]
    for _ in range(config.draws):
        if d.kind=='TRIANGULAR':
            value=d.minimum if d.minimum==d.maximum else rng.triangular(d.minimum,d.maximum,d.mode)
        else:
            u=rng.random();cumulative=0;value=d.values[-1]
            for v,w in zip(d.values,d.weights):
                cumulative+=w
                if u<cumulative: value=v;break
        values.append(value)
    return values


def summarize(values,alpha=.95):
    ordered=sorted(values);n=len(ordered)
    if not n: return None
    def q(p): return ordered[max(0,min(n-1,math.ceil(p*n)-1))]
    mean=fmean(values);z=q(alpha)
    # Finite-sample variational CVaR includes the correct fractional mass at ties.
    cvar=z+fmean(max(v-z,0) for v in values)/(1-alpha)
    half=fmean(values[:max(1,n//2)])
    return dict(mean=mean,median=q(.5),p05=q(.05),p95=q(.95),var=z,cvar=cvar,alpha=alpha,
        quantileConvention='Inverse empirical CDF (ceil(p*n)-1); CVaR = z + mean((loss-z)+)/(1-alpha)',
        numericalMeanStdError=stdev(values)/math.sqrt(n) if n>1 else None,
        convergence=dict(firstHalfMean=half,fullMean=mean,absoluteDrift=abs(mean-half)),
        meaning='Numerical sampling error is separate from unvalidated input/model uncertainty')


def simulate(context:CommercialContext,problem:dict,at,config:Simulation,*,checkpoint=None):
    if checkpoint: checkpoint()
    if config.mode=='EMPIRICAL_SHADOW':
        return dict(version=VERSION,mode=config.mode,status='COLLECTING',independentOperationalTargets=0,
            reason='No qualified downstream handling-error cohort is bound to this target, horizon and availability. Daily weather residuals do not calibrate it.',
            fallback='Existing unweighted closure stress/minimax remains available; no substitute distribution invented.')
    if config.draws*max(1,len(context.consignments))*len(problem['options'])>100000: raise ValueError('Requested sample/consignment budget exceeds the bounded study; reduce draws or split the study')
    deterministic=evaluate(context,problem,at)
    world=draw_world(config)  # Sample once, before looking at candidate order.
    ids=sorted(o['optionId'] for o in deterministic['options']);base=deterministic['baselineOptionId']
    losses={i:[] for i in ids};failures={i:0 for i in ids};missing={i:False for i in ids};regrets={i:[] for i in ids};event_hours={i:[] for i in ids}
    for delay in world:
        if checkpoint: checkpoint()
        result=evaluate(context,problem,at,delay=Decimal(str(delay)))
        rows={o['optionId']:o for o in result['options']};sample_losses={}
        for i in ids:
            row=rows[i];loss=float(row['supportedComponentTotal']);losses[i].append(loss)
            missing[i]=missing[i] or bool(row['missingComponents'])
            failures[i]+=bool(row['reasons'])
            sample_losses[i]=loss
            event_hours[i].append(max([max(0,-(s['slackHours'] or 0)) for s in row['consignments']]+[0]))
        best=min(sample_losses.values())
        for i in ids: regrets[i].append(sample_losses[i]-best)
    rows=[]
    for i in ids:
        complete=not missing[i]
        stats=summarize(losses[i],config.alpha) if complete else None
        score=(stats['mean']+config.tailPreference*(stats['cvar']-stats['mean'])) if stats and failures[i]==0 else None
        rows.append(dict(optionId=i,supportedCost=stats,currency=context.currency,score=score,
            conditionalConstraintFailureFrequency=failures[i]/config.draws,
            eventDefinition='At least one required declared commitment/operating/review gate fails in this assumed world; not a calibrated real-event probability',
            pairedDeltaVsCurrent=summarize([a-b for a,b in zip(losses[i],losses[base])],config.alpha) if complete and not missing[base] else None,
            regret=summarize(regrets[i],config.alpha) if complete and not any(missing.values()) else None,
            conditionalLateHours=summarize(event_hours[i],config.alpha),
            missingBasis=missing[i]))
    candidates=[r for r in rows if r['score'] is not None]
    pick=min(candidates,key=lambda r:(r['score'],r['optionId']!=base,r['optionId']))['optionId'] if candidates and not any(missing.values()) else None
    points=config.distribution.values if config.distribution.kind=='DISCRETE' else [config.distribution.minimum,config.distribution.mode,config.distribution.maximum]
    sensitivity=[dict(handlingDelayHours=d,conditionalPick=evaluate(context,problem,at,delay=Decimal(str(d)))['commercialPick']) for d in sorted(set(points))]
    if checkpoint: checkpoint()
    return dict(version=VERSION,mode=config.mode,status='SHADOW',samplerVersion=SAMPLER,seed=config.seed,draws=config.draws,
        independentOperationalTargets=0,inputHash=digest(context.model_dump(mode='json')),worldSampleHash=digest(world),
        commonRandomNumbers=True,dependency=config.distribution.dependency,distribution=config.distribution.model_dump(mode='json'),
        alpha=config.alpha,tailPreference=config.tailPreference,baselineOptionId=base,incumbentPick=deterministic['incumbentPick'],
        deterministicPick=deterministic['commercialPick'],conditionalShadowPick=pick,options=rows,sensitivity=sensitivity,
        limits=['Conditional simulated frequencies; no calibrated operational risk or validated superiority.',
            'Only additional downstream handling delay varies. Physical passage, hourly weather gates and fuel remain frozen.',
            'One shared shock across all candidates/consignments; other dependence structures are not identified.',
            'No safety/restriction gate is traded for money; missing material costs prevent a total-cost pick.'])
