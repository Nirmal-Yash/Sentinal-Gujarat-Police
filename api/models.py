import uuid, os
from datetime import datetime, date
from typing import Any, Optional
from sqlalchemy import Column, String, Float, Boolean, DateTime, Date, Text, Integer, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict, Field
from database import Base


class Camera(Base):
    __tablename__ = "cameras"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_id    = Column(Integer, unique=True)
    name         = Column(String(255), nullable=False)
    location     = Column(String(255), default="")
    lat          = Column(Float)
    lng          = Column(Float)
    rtsp_url     = Column(String(512))
    hls_url      = Column(String(512), default="")
    whep_url     = Column(String(512), default="")
    codec        = Column(String(20))
    width        = Column(Integer)
    height       = Column(Integer)
    fps          = Column(Float)
    status       = Column(String(50),  default="active")
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    department = Column(String(255), default="Unassigned")
    owner_organization = Column(String(255), default="Unassigned")
    camera_type = Column(String(100), default="fixed")
    connectivity_status = Column(String(50), default="unknown")
    protocol = Column(String(32), default="rtsp")
    source_system = Column(String(255), default="")
    storage_type = Column(String(100), default="")
    retention_days = Column(Integer)
    analytics_capabilities = Column(JSONB, default=list)
    maintenance_status = Column(String(50), default="unknown")
    maintenance_due_at = Column(DateTime(timezone=True))
    observed_codec = Column(String(64))
    observed_width = Column(Integer)
    observed_height = Column(Integer)
    observed_fps = Column(Float)
    observed_at = Column(DateTime(timezone=True))
    health_status = Column(String(50), default="unknown")
    last_frame_at = Column(DateTime(timezone=True))
    reconnect_count = Column(Integer, default=0)
    decode_failure_count = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    external_id = Column(String(255))
    installation_date = Column(Date)
    ptz_capable = Column(Boolean, default=False)
    night_vision_capable = Column(Boolean, default=False)
    coord_source = Column(String(32), default="unknown")
    coord_confidence = Column(Float)
    vendor_id = Column(UUID(as_uuid=True))
    model_id = Column(UUID(as_uuid=True))

    # API read-model precedence: current ingestion observation first, then an
    # explicitly configured value, otherwise None (shown as N/A by the UI).
    @property
    def effective_codec(self):
        return self.observed_codec or self.codec

    @property
    def effective_width(self):
        return self.observed_width if self.observed_width is not None else self.width

    @property
    def effective_height(self):
        return self.observed_height if self.observed_height is not None else self.height

    @property
    def effective_fps(self):
        return self.observed_fps if self.observed_fps is not None else self.fps

    @property
    def stream_url(self):
        """Browser-playable MP4 fallback derived from the canonical stream ID."""
        if self.stream_id is None:
            return None
        host = os.getenv("PLAYBACK_HOST", "live.corp8.cloud")
        return f"https://{host}/stream/{self.stream_id}"


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
    lat: Optional[float]; lng: Optional[float]; hls_url: str; whep_url: str; stream_url: Optional[str]
    codec: Optional[str]; width: Optional[int]; height: Optional[int]; fps: Optional[float]
    effective_codec: Optional[str]; effective_width: Optional[int]
    effective_height: Optional[int]; effective_fps: Optional[float]
    status: str; health_status: str; connectivity_status: str
    department: str; owner_organization: str; camera_type: str; protocol: str
    source_system: str; storage_type: str; retention_days: Optional[int]
    analytics_capabilities: Any; maintenance_status: str
    observed_at: Optional[datetime]; last_frame_at: Optional[datetime]
    external_id: Optional[str]; installation_date: Optional[date]
    ptz_capable: bool; night_vision_capable: bool
    coord_source: str; coord_confidence: Optional[float]
    vendor_id: Optional[uuid.UUID]; model_id: Optional[uuid.UUID]
    created_at: datetime; updated_at: datetime


class CameraCreate(BaseModel):
    """Manual/API onboarding payload.  Stream credentials stay write-only."""
    stream_id: Optional[int] = Field(None, ge=0)
    name: str = Field(min_length=1, max_length=255)
    location: str = ""
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    rtsp_url: Optional[str] = Field(None, max_length=512)
    hls_url: str = ""
    whep_url: str = ""
    department: str = "Unassigned"
    owner_organization: str = "Unassigned"
    camera_type: str = "fixed"
    protocol: str = "rtsp"
    source_system: str = ""
    external_id: Optional[str] = Field(None, max_length=255)
    storage_type: str = ""
    retention_days: Optional[int] = Field(None, ge=0)
    analytics_capabilities: list[str] = Field(default_factory=list)
    installation_date: Optional[date] = None
    ptz_capable: bool = False
    night_vision_capable: bool = False
    coord_source: str = "manual"
    coord_confidence: Optional[float] = Field(1.0, ge=0, le=1)
    vendor_id: Optional[uuid.UUID] = None
    model_id: Optional[uuid.UUID] = None


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
