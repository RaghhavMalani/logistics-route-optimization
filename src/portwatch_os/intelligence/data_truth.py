"""Public presentation contract. Unknown provenance is a first-class value."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel,ConfigDict

Origin=Literal['OFFICIAL_REPORT','REPORTED_EVENT','TRANSPONDER_OBSERVATION','PROVIDER_FORECAST','REANALYSIS','DERIVED_METRIC','OPERATOR_DECLARATION','SIMULATION','REFERENCE','UNKNOWN']
Freshness=Literal['CURRENT','LATEST_AVAILABLE','CACHED','STALE','HISTORICAL','CONNECTING','UNAVAILABLE','UNKNOWN']
Execution=Literal['DEMO_WORKFLOW','SIMULATED_OUTCOME','REPORTED_CONTEXT','CONFIRMED_SCOPED_OUTCOME','COLLECTING','SHADOW','REJECTED','UNKNOWN']


class DataTruth(BaseModel):
    model_config=ConfigDict(extra='allow')
    origin: Origin = 'UNKNOWN'
    freshness: Freshness = 'UNKNOWN'
    execution: Execution = 'UNKNOWN'
    provider: str | None = None
    product: str | None = None
    publishedAt: str | None = None
    firstAvailableAt: str | None = None
    lastSuccessfulCheckAt: str | None = None
    timePrecision: str | None = None
    sha256: str | None = None
