import uuid
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, Integer, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict
from database import Base


class Camera(Base):
    __tablename__ = "cameras"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_id    = Column(Integer, unique=True)
    name         = Column(String(255), nullable=False)
    location     = Column(String(255), default="")
    lat          = Column(Float, default=22.3039)
    lng          = Column(Float, default=70.8022)
    rtsp_url     = Column(String(512), nullable=False)
    hls_url      = Column(String(512), default="")
    whep_url     = Column(String(512), default="")
    codec        = Column(String(20),  default="H.264")
    width        = Column(Integer,     default=1280)
    height       = Column(Integer,     default=720)
    fps          = Column(Float,       default=25)
    status       = Column(String(50),  default="active")
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    detection_id    = Column(String)
    cam_id          = Column(UUID(as_uuid=True))
    alert_type      = Column(String(100), nullable=False)
    priority        = Column(String(20),  default="MEDIUM")
    confidence      = Column(Float,       default=0.0)
    entity_type     = Column(String(50),  default="unknown")
    details         = Column(JSONB,       default=dict)
    acknowledged    = Column(Boolean,     default=False)
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(255))
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


class WatchlistEntry(Base):
    __tablename__ = "watchlist"
    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name           = Column(String(255), nullable=False)
    entity_type    = Column(String(50),  default="person")
    description    = Column(Text,        default="")
    plate_number   = Column(String(50))
    embedding      = Column(Vector(512))
    alert_priority = Column(String(20),  default="HIGH")
    is_active      = Column(Boolean,     default=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)


class Detection(Base):
    __tablename__ = "detections"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cam_id           = Column(UUID(as_uuid=True))
    timestamp        = Column(DateTime(timezone=True))
    pts_ms           = Column(BigInteger, default=0)
    detection_type   = Column(String(50))
    bbox             = Column(JSONB)
    confidence       = Column(Float)
    track_id         = Column(String(255))
    global_track_id  = Column(String(255))
    plate_text       = Column(String(100))
    anomaly_score    = Column(Float,      default=0)
    embedding        = Column(Vector(512))
    # NOTE: 'metadata' is reserved by SQLAlchemy DeclarativeBase.
    # Column is aliased to the DB column name "metadata" via the first positional arg.
    det_metadata     = Column("metadata", JSONB, default=dict)
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─── Pydantic schemas ─────────────────────────────────────────────────────────
class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; stream_id: Optional[int]; name: str; location: str
    lat: float; lng: float; rtsp_url: str; hls_url: str; whep_url: str
    codec: str; width: int; height: int; fps: float
    status: str; created_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; cam_id: Optional[uuid.UUID]; alert_type: str
    priority: str; confidence: float; entity_type: str
    details: Any; acknowledged: bool; created_at: datetime


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; name: str; entity_type: str; description: str
    plate_number: Optional[str]; alert_priority: str
    is_active: bool; created_at: datetime


class WatchlistCreate(BaseModel):
    name: str
    entity_type: str = "person"
    description: str = ""
    plate_number: Optional[str] = None
    alert_priority: str = "HIGH"
