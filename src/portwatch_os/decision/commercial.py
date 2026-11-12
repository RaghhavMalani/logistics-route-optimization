"""Versioned Company-only commercial shadow over frozen passage results.

No operational ranking changes. Money is decimal and party-scoped. Missing
terms remain missing; declarations and conditional events are not actuals.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

VERSION = 'commercial-components-v1'
POLICY = 'declared-company-component-policy-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode()).hexdigest()


def instant(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    if not isinstance(at,datetime) or at.tzinfo is None or at.utcoffset() is None: raise ValueError('An aware timestamp is required')
    return at.astimezone(timezone.utc)


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class Amount(Strict):
    amount: Decimal = Field(ge=0,max_digits=22,decimal_places=6)
    currency: str = Field(pattern=r'^[A-Z]{3}$')


class Basis(Strict):
    kind: Literal['OPERATOR_DECLARATION','SIMULATION','AUTHORIZED_RECORD']
    source: str = Field(min_length=3,max_length=400)
    actor: str = Field(min_length=1,max_length=120)
    firstAvailableAt: datetime
    applicableFrom: datetime
    applicableThrough: datetime
    access: Literal['COMPANY_PRIVATE'] = 'COMPANY_PRIVATE'

    @field_validator('firstAvailableAt','applicableFrom','applicableThrough')
    @classmethod
    def aware(cls,v): return instant(v)

    @model_validator(mode='after')
    def interval(self):
        if self.applicableThrough<=self.applicableFrom: raise ValueError('Basis interval must be increasing')
        return self


class Party(Strict):
    id: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=120)
    roles: list[Literal['SHIPOWNER','OPERATOR','CARRIER','CHARTERER','CARGO_OWNER','SHIPPER','CONSIGNEE']] = Field(min_length=1)


class Penalty(Strict):
    payer: str
    beneficiary: str
    ratePerHour: Amount
    graceHours: Decimal = Field(default=Decimal(0),ge=0,le=87600)
    cap: Amount | None = None
    contractBasis: str = Field(min_length=3,max_length=400)


T = TypeVar("T")
Nonnegative = Annotated[Decimal, Field(ge=0, le=1_000_000_000)]
Fraction = Annotated[Decimal, Field(ge=0, le=1)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Sourced(Strict, Generic[T]):
    """Basis describes the term; the enclosing Consignment records its availability."""

    value: T
    basis: Literal["declared", "contract", "tariff", "assumption"]
    source: str = Field(min_length=3, max_length=400)


class LateCharge(Strict):
    amount: Amount
    unit: Literal["per_day", "flat"]


class WarRiskTerm(Strict):
    area: str = Field(min_length=1, max_length=100)
    required: Sourced[bool]
    premiumRate: Sourced[Fraction] | None = None


class CargoRiskTerms(Strict):
    """Optional commercial terms for the stochastic study, separate from feasibility."""

    commodityHsCode: Sourced[Annotated[str, Field(pattern=r"^[0-9]{2,10}$")]] | None = None
    currency: Sourced[Currency] | None = None
    cifValue: Sourced[Amount] | None = None
    insuredValue: Sourced[Amount] | None = None
    handlingClass: Sourced[Literal["dry", "reefer", "DG"]] | None = None
    reeferSetPointC: Sourced[Annotated[Decimal, Field(ge=-100, le=100)]] | None = None
    maxUnpoweredHours: Sourced[Nonnegative] | None = None
    remainingShelfLifeHours: Sourced[Nonnegative] | None = None
    imdgClass: Sourced[Annotated[str, Field(pattern=r"^[1-9](?:\.[1-6])?$")]] | None = None
    deliveryDeadline: Sourced[datetime] | None = None
    latePenalty: Sourced[LateCharge] | None = None
    freeTimeHours: Sourced[Nonnegative] | None = None
    detentionFreeHours: Sourced[Nonnegative] | None = None
    demurrageRatePerDay: Sourced[Amount] | None = None
    detentionRatePerDay: Sourced[Amount] | None = None
    annualInventoryRate: Sourced[Fraction] | None = None
    priority: Sourced[Literal[1, 2, 3]] | None = None
    margin: Sourced[Amount] | None = None
    cargoPolicyRate: Sourced[Fraction] | None = None
    deductible: Sourced[Amount] | None = None
    separateDeductibleEventProbability: Sourced[Fraction] | None = None
    excludedAreas: Sourced[list[str]] | None = None
    warRiskAreas: Sourced[list[WarRiskTerm]] | None = None
    generalAverageExposed: Sourced[bool] | None = None
    generalAverageContribution: Sourced[Amount] | None = None
    generalAverageEventProbability: Sourced[Fraction] | None = None

    @field_validator("deliveryDeadline")
    @classmethod
    def aware_deadline(cls, term):
        return term.model_copy(update={"value": instant(term.value)}) if term else None

    @model_validator(mode="after")
    def unique_war_areas(self):
        if self.warRiskAreas:
            areas = [area.area.casefold().strip() for area in self.warRiskAreas.value]
            if len(areas) != len(set(areas)) or "" in areas:
                raise ValueError("War-risk areas must have distinct names")
        return self


class Consignment(Strict):
    id: str = Field(min_length=1,max_length=80)
    goodsClass: str = Field(min_length=1,max_length=100)
    quantity: Decimal | None = Field(default=None,ge=0)
    quantityUnit: str | None = Field(default=None,max_length=40)
    teu: Decimal | None = Field(default=None,ge=0)
    weightTonnes: Decimal | None = Field(default=None,ge=0)
    hsCode: str | None = Field(default=None,pattern=r'^\d{2,6}$')
    hsVersion: str | None = None
    origin: str | None = None
    destinationPort: str
    finalLocation: str | None = None
    ownerParty: str | None = None
    transitRiskParty: str | None = None
    delayCostParty: str | None = None
    consigneeParty: str | None = None
    invoiceValue: Amount | None = None
    replacementValue: Amount | None = None
    insuredValue: Amount | None = None
    incoterm: str | None = None
    incotermVersion: str | None = None
    namedPlace: str | None = None
    allocationBasis: str | None = None
    event: Literal['CONDITIONAL_APPROACH','CONDITIONAL_CARGO_READY','DECLARED_FINAL_DELIVERY']
    deadline: datetime | None = None
    required: bool = False
    deliveryOffsetHours: Decimal | None = Field(default=None,ge=0,le=87600)
    offsetBasis: str | None = Field(default=None,max_length=400)
    cargoCommitment: dict | None = None
    remainingShelfLifeHours: Decimal | None = Field(default=None,ge=0)
    shelfLifeReferenceAt: datetime | None = None
    temperatureRequirement: str | None = None
    handlingNeeds: str | None = None
    penalty: Penalty | None = None
    stockoutConsequence: str | None = None
    inventoryUnits: Decimal | None = Field(default=None,ge=0)
    consumptionPerDay: Decimal | None = Field(default=None,gt=0)
    inventoryUnit: str | None = None
    basis: Basis

    riskTerms: CargoRiskTerms | None = None

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, serialize):
        result = serialize(self)
        if self.riskTerms is None:
            result.pop("riskTerms", None)
        return result

    @field_validator('deadline','shelfLifeReferenceAt')
    @classmethod
    def aware(cls,v): return instant(v) if v is not None else None


def insured_value_for_risk(shipment: Consignment) -> Sourced[Amount] | None:
    terms = shipment.riskTerms
    if terms and terms.insuredValue is not None:
        return terms.insuredValue
    if shipment.insuredValue is not None:
        return Sourced[Amount](
            value=shipment.insuredValue,
            basis="assumption" if shipment.basis.kind == "SIMULATION" else "declared",
            source=shipment.basis.source,
        )
    if terms and terms.cifValue is not None:
        cif = terms.cifValue
        return Sourced[Amount](
            value=Amount(
                amount=(cif.value.amount * Decimal("1.10")).quantize(Decimal("0.000001")),
                currency=cif.value.currency,
            ),
            basis="assumption",
            source="CIF × 1.10 modelling default; CIF basis: " + cif.source[:320],
        )
    return None


class Charge(Strict):
    id: str = Field(min_length=1,max_length=80)
    payer: str
    beneficiary: str
    kind: Literal['ELAPSED_FUTURE_TIME','WAIT_TIME','ADDITIONAL_HANDLING_DELAY','FIXED_COMPONENT','REVENUE']
    rate: Amount
    optionAmounts: dict[str,Amount] | None = None
    contractBasis: str = Field(min_length=3,max_length=400)
    interval: Literal['REMAINING_PASSAGE_ONLY'] = 'REMAINING_PASSAGE_ONLY'
    basis: Basis


class PolicyEvidence(Strict):
    id: str = Field(min_length=1,max_length=100)
    cover: Literal['CARGO','HULL_MACHINERY','PI_LIABILITY','WAR_STRIKES','LOSS_OF_HIRE','SPECIALIST']
    status: Literal['DECLARED_TERMS','TERMS_REVIEWED','BROKER_CONFIRMATION_REQUIRED']
    insuredParty: str
    shipmentIds: list[str] = Field(default_factory=list)
    vesselId: str | None = None
    insuredInterest: str | None = None
    insuredAmount: Amount | None = None
    limit: Amount | None = None
    deductible: Amount | None = None
    startsAt: datetime
    endsAt: datetime
    clauses: str | None = None
    exclusions: str | None = None
    geographicTerms: str | None = None
    notificationRequired: bool | None = None
    notificationEvidence: str | None = None
    additionalPremiumQuote: Amount | None = None
    quoteExpiresAt: datetime | None = None
    evidenceSha256: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    basis: Basis

    @field_validator('startsAt','endsAt','quoteExpiresAt')
    @classmethod
    def aware(cls,v): return instant(v) if v is not None else None

    @model_validator(mode='after')
    def interval(self):
        if self.endsAt<=self.startsAt: raise ValueError('Policy interval must increase')
        return self


class ResourceClaim(Strict):
    resourceId: str
    unit: Literal['TEU','REEFER_PLUG','USD_BUDGET']
    quantity: Decimal = Field(gt=0)
    capacity: Decimal | None = Field(default=None,ge=0)
    beginsAt: datetime
    endsAt: datetime
    basis: Basis

    @field_validator('beginsAt','endsAt')
    @classmethod
    def aware(cls,v): return instant(v)

    @model_validator(mode='after')
    def interval(self):
        if self.endsAt<=self.beginsAt: raise ValueError('Resource claim interval must increase')
        return self


class CommercialContext(Strict):
    schemaVersion: Literal['commercial-context-v1'] = 'commercial-context-v1'
    decisionId: str
    voyageId: str
    parties: list[Party] = Field(min_length=1,max_length=30)
    objectiveParty: str
    objective: Literal['SUPPORTED_COMPONENT_COST','DELIVERY_COMMITMENT','DECLARED_MARGIN']
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    accountingScope: str = Field(min_length=5,max_length=400)
    materialComponents: list[str] = Field(min_length=1,max_length=40)
    includePassageFuel: bool = False
    fuelPayer: str | None = None
    consignments: list[Consignment] = Field(default_factory=list,max_length=50)
    charges: list[Charge] = Field(default_factory=list,max_length=50)
    policies: list[PolicyEvidence] = Field(default_factory=list,max_length=30)
    insuranceReviewRequired: bool = False
    marketEvidenceIds: list[str] = Field(default_factory=list,max_length=20)
    listedAreaEvidenceIds: list[str] = Field(default_factory=list,max_length=20)
    resources: list[ResourceClaim] = Field(default_factory=list,max_length=30)
    decisionDeadline: datetime | None = None
    basis: Basis

    @field_validator('decisionDeadline')
    @classmethod
    def aware(cls,v): return instant(v) if v else None

    @model_validator(mode='after')
    def identities(self):
        ids=[p.id for p in self.parties]
        if len(set(ids))!=len(ids) or self.objectiveParty not in ids: raise ValueError('Distinct parties and an existing objective party are required')
        if self.fuelPayer is not None and self.fuelPayer not in ids: raise ValueError('Fuel payer must be a declared party')
        for values in (self.consignments,self.charges,self.policies):
            row_ids=[r.id for r in values]
            if len(set(row_ids))!=len(row_ids): raise ValueError('Duplicate shipment, charge or policy identities')
        for c in self.charges:
            if c.id.startswith('passage_fuel') or c.id.startswith('penalty:'): raise ValueError('Reserved calculated component identity; do not duplicate fuel or shipment penalties')
            if c.payer not in ids or c.beneficiary not in ids: raise ValueError('Every charge names known parties')
        for s in self.consignments:
            for p in (s.ownerParty,s.transitRiskParty,s.delayCostParty,s.consigneeParty):
                if p is not None and p not in ids: raise ValueError('Shipment party is not declared')
            if s.penalty and (s.penalty.payer not in ids or s.penalty.beneficiary not in ids): raise ValueError('Penalty parties are not declared')
            if s.quantity is not None and not s.quantityUnit: raise ValueError('Quantity requires its unit')
        for party in ids:
            kinds={c.kind for c in self.charges if c.payer==party}
            if 'ELAPSED_FUTURE_TIME' in kinds and 'WAIT_TIME' in kinds: raise ValueError('Elapsed time already includes waiting; overlapping charges are refused')
        return self


def _event(shipment,option,env,delay,at):
    issued_at=at
    clear=option.get('approachClearAt')
    if not clear: return None,'Conditional approach is unavailable'
    at=instant(clear)
    if shipment.event=='CONDITIONAL_CARGO_READY':
        if not shipment.cargoCommitment: return None,'A supported cargo-stage declaration is missing'
        from .passage_cargo import validate_commitment,evaluate_commitment
        commitment=validate_commitment(shipment.cargoCommitment,voyage_id=env['voyageId'],port_code=env['portCode'],at=issued_at)
        assessed=evaluate_commitment(commitment,clear_approach_at=clear,option_id=option['optionId'])
        ready=assessed.get('readinessAt')
        if not ready: return None,'Cargo readiness is incomplete'
        at=instant(ready)
    elif shipment.event=='DECLARED_FINAL_DELIVERY':
        if shipment.deliveryOffsetHours is None or not shipment.offsetBasis: return None,'Final-delivery offset and its assumption basis are missing'
        at+=timedelta(hours=float(shipment.deliveryOffsetHours))
    # Additional handling is applied once to downstream events, never to hourly weather.
    if shipment.event!='CONDITIONAL_APPROACH': at+=timedelta(hours=float(delay))
    return at,None


def insurance_review(context,env,at):
    result=[]
    through=max([instant(o['approachClearAt']) for o in env.get('passageComparison',{}).get('options',[]) if o.get('approachClearAt')]+[at])
    for p in context.policies:
        issues=[]
        if p.insuredParty not in {party.id for party in context.parties}: issues.append('Insured party is not declared')
        if not p.insuredInterest or p.insuredAmount is None: issues.append('Insured interest or amount is incomplete')
        if not p.vesselId and not p.shipmentIds: issues.append('Vessel/shipment scope is unspecified')
        if not p.geographicTerms or not p.clauses or p.exclusions is None: issues.append('Geographical terms, clauses or exclusions need review')
        if p.insuredAmount and any(m and m.currency!=p.insuredAmount.currency for m in (p.limit,p.deductible)): issues.append('Policy amount currencies do not match')
        if p.additionalPremiumQuote and not p.quoteExpiresAt: issues.append('Additional-premium quote validity is unknown')
        if not p.startsAt<=at or p.endsAt<through: issues.append('Policy dates do not cover the declared period')
        if p.vesselId and p.vesselId!=context.voyageId: issues.append('Vessel scope mismatch')
        if set(p.shipmentIds)-{s.id for s in context.consignments}: issues.append('Shipment scope mismatch')
        if p.quoteExpiresAt and p.quoteExpiresAt<at: issues.append('Additional-premium quote expired')
        if p.notificationRequired and not p.notificationEvidence: issues.append('Required notification evidence missing')
        if p.status!='TERMS_REVIEWED': issues.append('Terms require authorized review')
        if not p.evidenceSha256: issues.append('Policy original hash is missing')
        result.append(dict(id=p.id,cover=p.cover,status='EXPIRED' if p.endsAt<at else 'BROKER_CONFIRMATION_REQUIRED' if issues else 'TERMS_REVIEWED',issues=issues))
    if not result: result=[dict(id=None,cover=None,status='NO_POLICY_EVIDENCE',issues=['No policy evidence supplied; this is not a finding that the vessel is uninsured'])]
    return dict(policies=result,cleared=bool(context.policies) and all(r['status']=='TERMS_REVIEWED' for r in result),
        recovery=None,meaning='Terms screening only. Coverage, payable claims and war-event probabilities are not adjudicated.')


def require_commercial_current(problem,scoped):
    """Action-time private check with a role-safe refusal. No retained GET writes."""
    binding=problem.evidence.get('commercialReview')
    if not binding or scoped is None: return
    from fastapi import HTTPException
    from src.portwatch_os.decision.engine import get_engine
    from src.portwatch_os.clock import wall_now
    engine=get_engine();record=engine.ledger.get_decision(binding['recordId'])
    if record is None: raise HTTPException(409,'The bound Company commercial study is unavailable; fresh Company review is required')
    data=record.recommendation;source=engine.get(data['sourceDecisionId'])
    if source is None: raise HTTPException(409,'The source comparison is unavailable for commercial rechecking')
    env=source.evidence['currentEnvironment'];key=source.subject_id+':'+str((env.get('operationalEpisode') or {}).get('id'))
    if scoped.world.get('commercialLatest',{}).get(key)!=binding['recordId']:
        raise HTTPException(409,'Relevant Company commercial inputs changed; explicitly review a linked successor. Earlier approvals remain retained.')
    # wall-clock: approval/issue eligibility checks the real current expiry of private declarations and quotes.
    now=wall_now()
    try: current=evaluate(CommercialContext(**data['context']),source.to_dict(),now)
    except ValueError: raise HTTPException(409,'Company commercial declarations expired or changed; fresh review is required') from None
    selected=problem.human_choice or (problem.evidence.get('companyProposal') or {}).get('optionId')
    row=next((r for r in current['options'] if r['optionId']==selected),None)
    if row and row['reasons']: raise HTTPException(409,'The selected plan no longer passes its declared Company commercial/review gates; fresh Company review is required')


def resource_conflicts(context,others):
    """Half-open interval sweep; versions/calls must be deduplicated by caller."""
    groups={}
    for owner,claims in [('this',context.resources),*[(str(i),CommercialContext(**c).resources) for i,c in enumerate(others)]]:
        for r in claims: groups.setdefault((r.resourceId,r.unit),[]).append((owner,r))
    result=[]
    for (resource,unit),claims in groups.items():
        if not any(owner=='this' for owner,_ in claims): continue
        instants=sorted({t for _,r in claims for t in (r.beginsAt,r.endsAt)})
        for begins,ends in zip(instants,instants[1:]):
            active=[(owner,r) for owner,r in claims if r.beginsAt<=begins<r.endsAt]
            if not any(owner=='this' for owner,_ in active): continue
            used=sum((r.quantity for _,r in active),Decimal(0))
            caps=[r.capacity for _,r in active]
            capacity=min(caps) if caps and all(c is not None for c in caps) else None
            result.append(dict(resourceId=resource,unit=unit,beginsAt=begins.isoformat(),endsAt=ends.isoformat(),
                claimedQuantity=str(used),declaredCapacity=str(capacity) if capacity is not None else None,
                status='CAPACITY_UNKNOWN' if capacity is None else 'CONFLICT' if used>capacity else 'UNRESERVED_WITHIN_DECLARED_CAPACITY',
                meaning='Unreserved declarations only; no joint allocation or booking'))
    return result


def evaluate(context: CommercialContext,problem: dict,at: datetime,*,delay=Decimal(0)):
    at=instant(at);env=problem.get('evidence',{}).get('currentEnvironment',{});comparison=env.get('passageComparison')
    if not comparison: raise ValueError('Commercial v1 requires an existing declared-passage comparison; strategic rerouting remains outside this workflow')
    if context.decisionId!=problem['decisionId'] or context.voyageId!=problem['subject']['id']: raise ValueError('Commercial declaration must bind the exact voyage and comparison')
    if context.basis.firstAvailableAt>at or any(s.basis.firstAvailableAt>at for s in context.consignments): raise ValueError('Later-known declarations cannot enter this evaluation')
    for basis in [context.basis,*[c.basis for c in context.charges],*[s.basis for s in context.consignments],*[p.basis for p in context.policies],*[r.basis for r in context.resources]]:
        if basis.firstAvailableAt>at or not basis.applicableFrom<=at<=basis.applicableThrough: raise ValueError('Declaration availability or applicability does not cover this calculation')
    insurance=insurance_review(context,env,at)
    action_by={a['optionId']:a for a in problem['options']}
    options=[]
    for option in comparison['options']:
        reasons=[];missing=[];components=[];assessments=[]
        option_id=option['optionId'];action=action_by.get(option_id,{})
        previous_commercial_only=bool(action.get('rejectedBy')) and all(c.get('key')=='commercial_required_commitment' for c in action['rejectedBy'])
        if option.get('status')!='FEASIBLE' or (action.get('status')!='FEASIBLE' and not previous_commercial_only): reasons.append(option.get('reason') or 'Existing physical/operating gates reject this plan')
        clear=instant(option['approachClearAt']) if option.get('approachClearAt') else None
        common_hours=Decimal(str(option.get('commonElapsedSailingHours') or 0))
        sailing_hours=Decimal(str(option.get('futureSailingHours') if option.get('futureSailingHours') is not None else option.get('sailingHours') or 0))
        future_hours=sailing_hours+sum(Decimal(str(option.get(k) or 0)) for k in ('departureHoldHours','anchorageWaitHours'))
        for charge in context.charges:
            if charge.payer!=context.objectiveParty and charge.beneficiary!=context.objectiveParty: continue
            amount=charge.optionAmounts.get(option_id) if charge.optionAmounts is not None else charge.rate
            if amount is None: missing.append(charge.id);continue
            if amount.currency!=context.currency: missing.append(charge.id+' (currency mismatch; no conversion)');continue
            multiplier=Decimal(1)
            if charge.kind=='ELAPSED_FUTURE_TIME': multiplier=future_hours+delay
            elif charge.kind=='WAIT_TIME': multiplier=Decimal(str(option.get('anchorageWaitHours') or 0))
            elif charge.kind=='ADDITIONAL_HANDLING_DELAY': multiplier=delay
            sign=Decimal(0) if charge.beneficiary==charge.payer else Decimal(-1) if charge.beneficiary==context.objectiveParty else Decimal(1)
            components.append(dict(id=charge.id,amount=str(amount.amount*multiplier*sign),currency=context.currency,scope='VOYAGE_ONCE',kind=charge.kind))
        if context.includePassageFuel:
            if context.fuelPayer is None: missing.append('passage_fuel (payer unknown)')
            elif context.fuelPayer==context.objectiveParty:
                if common_hours: missing.append('passage_fuel (future-only fuel allocation unavailable)')
                fuel_components=[c for c in option.get('finance',{}).get('components',[]) if c.get('key','').endswith('_fuel')]
                # Existing financial serialization uses componentId in some retained versions.
                if not fuel_components: fuel_components=[c for c in option.get('finance',{}).get('components',[]) if 'fuel' in str(c.get('componentId','')).lower()]
                if not fuel_components: missing.append('passage_fuel')
                for c in fuel_components:
                    money=c.get('money')
                    if not isinstance(money,dict) or money.get('currency')!=context.currency or money.get('amount') is None: missing.append('passage_fuel');break
                    components.append(dict(id='passage_fuel:'+str(c.get('key') or c.get('componentId')),amount=str(Decimal(str(money['amount']))),currency=context.currency,scope='VOYAGE_ONCE',kind='FUEL'))
        for shipment in context.consignments:
            if shipment.destinationPort!=env['portCode']: reasons.append(shipment.id+': destination mismatch');continue
            event_at,error=_event(shipment,option,env,delay,at)
            slack=Decimal(str((shipment.deadline-event_at).total_seconds()/3600)) if shipment.deadline and event_at else None
            shelf_slack=None
            if shipment.remainingShelfLifeHours is not None:
                if shipment.shelfLifeReferenceAt is None or event_at is None: error=error or 'Shelf-life reference/event unavailable'
                else: shelf_slack=shipment.remainingShelfLifeHours-Decimal(str((event_at-shipment.shelfLifeReferenceAt).total_seconds()/3600))
            failed=(slack is not None and slack<0) or (shelf_slack is not None and shelf_slack<0)
            if shipment.required and (failed or error or slack is None): reasons.append(shipment.id+': required commitment '+('fails' if failed else 'is incomplete'))
            if shipment.penalty:
                p=shipment.penalty;key='penalty:'+shipment.id
                if p.payer==context.objectiveParty or p.beneficiary==context.objectiveParty:
                    if slack is None or p.ratePerHour.currency!=context.currency or (p.cap and p.cap.currency!=context.currency): missing.append(key)
                    else:
                        amount=max(Decimal(0),-slack-p.graceHours)*p.ratePerHour.amount
                        if p.cap: amount=min(amount,p.cap.amount)
                        if p.beneficiary==p.payer: amount=Decimal(0)
                        elif p.beneficiary==context.objectiveParty: amount=-amount
                        components.append(dict(id=key,amount=str(amount),currency=context.currency,scope='SHIPMENT',kind='DECLARED_PENALTY'))
            cover=shipment.inventoryUnits/shipment.consumptionPerDay if shipment.inventoryUnits is not None and shipment.consumptionPerDay is not None and shipment.inventoryUnit else None
            assessments.append(dict(shipmentId=shipment.id,event=shipment.event,eventAt=event_at.isoformat() if event_at else None,
                slackHours=float(slack) if slack is not None else None,shelfLifeSlackHours=float(shelf_slack) if shelf_slack is not None else None,
                required=shipment.required,status='FAILS' if failed else 'UNKNOWN' if error or slack is None else 'WITHIN_DECLARED_COMMITMENT',reason=error,
                stockCoverDays=str(cover) if cover is not None else None,deteriorationMoney=None))
        available={c['id'] for c in components}
        for key in context.materialComponents:
            if key=='passage_fuel' and any(k.startswith('passage_fuel:') for k in available): continue
            if key not in available: missing.append(key)
        if context.insuranceReviewRequired and not insurance['cleared']: reasons.append('Required insurance review remains incomplete')
        if context.decisionDeadline and at>context.decisionDeadline: reasons.append('Declared Company decision deadline has passed')
        total=sum((Decimal(c['amount']) for c in components),Decimal(0))
        options.append(dict(optionId=option_id,label=option['label'],status='REQUIRES_REVIEW' if reasons else 'INCOMPLETE_BASIS' if missing else 'CONDITIONALLY_FEASIBLE',
            reasons=reasons,missingComponents=sorted(set(missing)),components=components,supportedComponentTotal=str(total),
            comparableTotal=None if missing or reasons else str(total),currency=context.currency,consignments=assessments,
            approachClearAt=option.get('approachClearAt'),commonElapsedSailingHours=str(common_hours),futureDecisionHours=str(future_hours),modeledFuelTonnes=(option.get('fuel') or {}).get('totalTonnes')))
    eligible=[o for o in options if o['status']=='CONDITIONALLY_FEASIBLE']
    baseline=problem.get('baselineOptionId')
    # All compared candidates must have the same adequate scope; never omit missing costs from one side.
    pick=None
    if eligible and not any(o['missingComponents'] for o in options if not o['reasons']):
        pick=min(eligible,key=lambda o:(Decimal(o['comparableTotal']),o['optionId']!=baseline,o['optionId']))['optionId']
    if context.objective=='DELIVERY_COMMITMENT':
        if not any(s.required and s.deadline for s in context.consignments): pick=None
        else: pick=baseline if any(o['optionId']==baseline for o in eligible) else pick
    if context.objective=='DECLARED_MARGIN' and not any(c.kind=='REVENUE' for c in context.charges): pick=None
    return dict(version=VERSION,policyVersion=POLICY,execution='SHADOW',objective=context.objective,objectiveParty=context.objectiveParty,
        accountingScope=context.accountingScope,currency=context.currency,baselineOptionId=baseline,
        incumbentPick=(problem.get('evidence',{}).get('commercialReview') or {}).get('incumbentPick') or (problem.get('recommendation') or {}).get('optionId'),commercialPick=pick,
        decision='KEEP_CURRENT_PLAN' if pick==baseline and pick else 'CONDITIONAL_CANDIDATE' if pick else 'INCOMPLETE_BASIS',
        options=options,insurance=insurance,expectedRecovery=None,profit=None,
        limits=['Declared/modelled component comparison, not measured savings or complete voyage profit.','Invoice, replacement and insured values are separate and are not automatically losses.','No booking, insurer adjudication or operational policy adoption.'])
