# Backward-compatibility shim — import from new location
from app.schemas.target import (  # noqa: F401
    TargetTypeEnum, TargetCreate, TargetUpdate, TargetResponse,
    HealthResponse, RealtimeData, IndicatorData, QuoteResponse,
)
