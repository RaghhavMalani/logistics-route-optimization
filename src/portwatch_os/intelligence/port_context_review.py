"""Explicit operator criteria and consumed daily context, with no delay effect."""
import copy
import json
from . import public_port_context as source
from .public_ports import digest, stamp

VERSION='port-context-review-v1'


def view(world,at):
    fixture=world.get('illustrativeInputs',{}).get('portContext')
    if fixture:
        from src.portwatch_os.learning.weather_feedback import instant
        versions=[*world.get('illustrativeSourceHistory',[]),fixture]
        eligible=[v for v in versions if instant(v['availableAt'])<=at]
        selected=max(eligible,key=lambda v:instant(v['availableAt'])) if eligible else {'status':'UNAVAILABLE','metrics':[],'reason':'Software fixture was not yet available at this inspection time'}
        return {**copy.deepcopy(selected),'asOf':stamp(at),'evidenceKind':'SOFTWARE_LIFECYCLE_FIXTURE','realOperationalTargetsResolved':0}
    return source.retained(as_of=at)


def rule_for(world,vessel_id):
    rule=(world.get('portContextRules') or {}).get(vessel_id)
    vessel=next((v for v in world.get('fleet',[]) if v.get('id')==vessel_id),{})
    return rule if isinstance(rule,dict) and rule.get('episodeId')==(vessel.get('operationalEpisode') or {}).get('id') and rule.get('portCode')==vessel.get('portCode') else None


def freeze(scoped,vessel_id,selections,*,at):
    if selections is None:return []
    if not isinstance(selections,list) or len(selections)!=1:raise ValueError('Select one exact daily port-context review or omit it')
    selection=selections[0]
    if not isinstance(selection,dict) or selection.get('acknowledged') is not True:raise ValueError('Explicit port-context acknowledgement required')
    rule=rule_for(scoped.world,vessel_id);current=view(scoped.world,at)
    if not rule or current.get('portCode')!=rule['portCode'] or selection.get('ruleId')!=rule['id'] or selection.get('revisionId')!=current.get('revisionId'):raise ValueError('Review the exact current product and owned-call operator criterion')
    metric=next((m for m in current['metrics'] if m['id']==rule['metricId']),None)
    simulated=current.get('evidenceKind')=='SOFTWARE_LIFECYCLE_FIXTURE'
    if not metric or metric.get('eligibility')!='CURRENT_ELIGIBLE' or current.get('status')!='CURRENT_ELIGIBLE':raise ValueError('Current eligible section/metric is required; latest available alone is insufficient')
    binding={'contractVersion':VERSION,'sourceFamily':source.FAMILY,'portCode':'INPRT','snapshotId':current['snapshotId'],
             'revisionId':current['revisionId'],'originalSha256':current.get('originalSha256'), 'source':current.get('source'),
             'reportDate':current['reportDate'],'availableAt':current['availableAt'],'sourceCheckedAt':current['lastSuccessfulCheckAt'],
             'metric':copy.deepcopy(metric),'rule':copy.deepcopy(rule),'reviewTriggered':metric['value']>=rule['threshold'],
             'policyVersion':current['policyVersion'],'evidenceKind':'SOFTWARE_LIFECYCLE_FIXTURE' if simulated else 'OFFICIAL_PUBLIC_REPORT_CONTEXT',
             'calculationRole':'CONTEXT_ONLY_OPERATOR_REVIEW','numericalEffect':None,'consumedAt':stamp(at),
             'meaning':'Reported rows evaluated against an operator review threshold. No individual delay, closure, clearance, capacity reservation or observed demo hull is established.'}
    binding['id']=digest(json.dumps(binding,sort_keys=True));return [binding]


def assess(bindings,world,current,*,at):
    findings=[]
    for binding in bindings or []:
        rule=binding['rule'];metric=next((m for m in current.get('metrics',[]) if m['id']==rule['metricId']),None)
        changes=[]
        for key,before,after in [('metricValue',binding['metric']['value'],metric.get('value') if metric else None),
            ('sectionAsOf',binding['metric'].get('asOf') or binding['metric'].get('dateScope'),(metric.get('asOf') or metric.get('dateScope')) if metric else None),
            ('operatorRule',rule,rule_for(world,rule['vesselId'])),('policyVersion',binding['policyVersion'],current.get('policyVersion'))]:
            if before!=after:changes.append({'field':key,'before':before,'after':after})
        unavailable=current.get('portCode')!=rule['portCode'] or current.get('status')!='CURRENT_ELIGIBLE' or not metric or metric.get('eligibility')!='CURRENT_ELIGIBLE'
        if changes or unavailable:
            findings.append({'code':'PORT_CONTEXT_REVIEW_CHANGED' if changes else 'PORT_CONTEXT_NO_LONGER_ELIGIBLE',
                'text':'Consumed daily context/criterion changed or lost current eligibility; explicitly review a linked successor.',
                'noticeId':source.FAMILY+':INPRT','basis':'portContextBindings:'+binding['id'],
                'consumedRevisionId':binding['revisionId'],'currentRevisionId':current.get('revisionId'),
                'consumedAvailableAt':binding['availableAt'],'currentAvailableAt':current.get('availableAt'),
                'changes':changes,'unknown':'Individual wait, actual passage, berth access and savings remain unknown.',
                'nextAction':'Inspect the affected metric and operator criterion, then explicitly create and review a successor.'})
    return findings


def annotate(projection,world,decisions,current,*,at):
    by_id={d['decisionId']:d for d in decisions}
    for row in projection['rows']:
        row['portContext']=None
        if row['destinationPort']!='INPRT':continue
        rule=rule_for(world,row['vessel']['id']);metric=next((m for m in current.get('metrics',[]) if rule and m['id']==rule['metricId']),None)
        decision=by_id.get(row['currentPlan'].get('decisionId'),{});basis=(decision.get('evidence') or {}).get('currentEnvironment') or {}
        consumed=basis.get('portContextBindings') or []
        triggered=bool(rule and current.get('portCode')==rule['portCode'] and metric and metric.get('value') is not None and metric.get('eligibility')=='CURRENT_ELIGIBLE' and current.get('status')=='CURRENT_ELIGIBLE' and metric['value']>=rule['threshold'])
        separate=triggered and not consumed and not row['workflow'].get('completed')
        row['portContext']={'sourceFamily':source.FAMILY,'status':current['status'],'reportDate':current.get('reportDate'),
            'revisionId':current.get('revisionId'),'metric':metric,'rule':rule,'reviewRequired':separate,'responsibleRole':'SHIPPING_COMPANY' if separate else None,
            'reason':'Destination association only; this fictional hull is not matched to a report vessel. '+('The acknowledged operator count criterion is met; no hours are inferred.' if separate else 'No separate unconsumed operator review trigger is established.')}
        if separate:row['reasons'].append({'code':'PORT_CONTEXT_OPERATOR_REVIEW','text':'A reported destination metric crossed the acknowledged operator review threshold; workflow next-role remains separate.','basis':rule['id']})
    counts={}
    for row in projection['rows']:
        for code in {r['code'] for r in row['reasons']}:counts[code]=counts.get(code,0)+1
    projection['reasonCounts']=dict(sorted(counts.items()));projection['portContextPolicyVersion']=VERSION
    return projection
