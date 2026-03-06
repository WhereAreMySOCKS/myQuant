# Backward-compatibility shim — import from new locations
from app.core.database import engine, SessionLocal, Base, init_db, get_db  # noqa: F401
from app.models.target import Target, TargetType, SecurityInfo  # noqa: F401
