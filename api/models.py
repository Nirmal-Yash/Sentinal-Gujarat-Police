import os, time, uuid, re
from datetime import datetime, date
from typing import Any, Optional
from sqlalchemy import Column, String, Float, Boolean, DateTime, Date, Text, Integer, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from database import Base


class CameraGroup(Base):
    __tablename__ = "camera_groups"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    code = Column(String(64), unique=True, nullable=False)
    parent_id = Column(UUID(as_uuid=True), nullable=True)
    group_type = Column(String(64), default="zone")
    description = Column(Text, default="")
    metadata_json = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Camera(Base):
    __tablename__ = "cameras"
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); stream_id=Column(Integer,unique=True); name=Column(String(255),nullable=False)
    location=Column(String(255),default=""); lat=Column(Float); lng=Column(Float); rtsp_url=Column(String(512)); hls_url=Column(String(512),default=""); whep_url=Column(String(512),default="")
    codec=Column(String(20)); width=Column(Integer); height=Column(Integer); fps=Column(Float); status=Column(String(50),default="active")
    created_at=Column(DateTime(timezone=True),default=datetime.utcnow); last_seen_at=Column(DateTime(timezone=True),default=datetime.utcnow)
    department=Column(String(255),default="Unassigned"); owner_organization=Column(String(255),default="Unassigned"); camera_type=Column(String(100),default="fixed")
    connectivity_status=Column(String(50),default="unknown"); protocol=Column(String(32),default="rtsp"); source_system=Column(String(255),default=""); storage_type=Column(String(100),default=""); retention_days=Column(Integer)
    analytics_capabilities=Column(JSONB,default=list); maintenance_status=Column(String(50),default="unknown"); maintenance_due_at=Column(DateTime(timezone=True))
    observed_codec=Column(String(64)); observed_width=Column(Integer); observed_height=Column(Integer); observed_fps=Column(Float); observed_source_fps=Column(Float); observed_decode_fps=Column(Float); observed_published_fps=Column(Float); observed_at=Column(DateTime(timezone=True))
    health_status=Column(String(50),default="unknown"); last_frame_at=Column(DateTime(timezone=True)); reconnect_count=Column(Integer,default=0); decode_failure_count=Column(Integer,default=0); updated_at=Column(DateTime(timezone=True),default=datetime.utcnow)
    external_id=Column(String(255)); installation_date=Column(Date); ptz_capable=Column(Boolean,default=False); night_vision_capable=Column(Boolean,default=False); coord_source=Column(String(32),default="unknown"); coord_confidence=Column(Float)
    department_source=Column(String(32),default="unknown"); department_confidence=Column(Float); vendor_id=Column(UUID(as_uuid=True)); model_id=Column(UUID(as_uuid=True)); processing_fps_category=Column(String(32),default="pedestrian",nullable=False)
    group_id=Column(UUID(as_uuid=True),nullable=True)
    zone=Column(String(128),default="Ahmedabad Zone",nullable=False)
    district=Column(String(128),default="Ahmedabad",nullable=False)
    subdivision=Column(String(128),default="City Division",nullable=False)
    police_station=Column(String(128),default="City Police Station",nullable=False)
    @property
    def effective_codec(self): return self.observed_codec or self.codec
    @property
    def effective_width(self): return self.observed_width if self.observed_width is not None else self.width
    @property
    def effective_height(self): return self.observed_height if self.observed_height is not None else self.height
    @property
    def effective_fps(self): return self.observed_source_fps if self.observed_source_fps is not None else (self.observed_fps if self.observed_fps is not None else self.fps)
    @property
    def playback_id(self):
        external = (self.external_id or "").strip()
        if re.fullmatch(r"cam\d{2}", external, re.IGNORECASE): return external.lower()
        if self.stream_id is None: return None
        return f"cam{int(self.stream_id):02d}"
    @property
    def stream_url(self):
        if self.rtsp_url: return self.rtsp_url
        if self.stream_id is None:return None
        return f"rtsp://{os.getenv('RTSP_HOST_IP','103.250.160.189')}:{int(os.getenv('RTSP_PORT','8554'))}/stream/cam{int(self.stream_id):02d}"

class Alert(Base):
    __tablename__="alerts"
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); detection_id=Column(String); cam_id=Column(UUID(as_uuid=True)); alert_type=Column(String(100),nullable=False)
    priority=Column(String(20),default="MEDIUM"); confidence=Column(Float,default=0.0); entity_type=Column(String(50),default="unknown"); details=Column(JSONB,default=dict)
    acknowledged=Column(Boolean,default=False); acknowledged_at=Column(DateTime(timezone=True)); acknowledged_by=Column(String(255)); status=Column(String(32),default="NEW")
    created_at=Column(DateTime(timezone=True),default=datetime.utcnow); updated_at=Column(DateTime(timezone=True),default=datetime.utcnow); resolved_at=Column(DateTime(timezone=True)); resolved_by=Column(String(255)); closed_at=Column(DateTime(timezone=True)); closed_by=Column(String(255))

class WatchlistEntry(Base):
    __tablename__="watchlist"
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); name=Column(String(255),nullable=False); entity_type=Column(String(50),default="person"); description=Column(Text,default=""); plate_number=Column(String(50)); embedding=Column(Vector(512)); alert_priority=Column(String(20),default="HIGH"); is_active=Column(Boolean,default=True); created_at=Column(DateTime(timezone=True),default=datetime.utcnow)

class Detection(Base):
    __tablename__="detections"
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); cam_id=Column(UUID(as_uuid=True)); timestamp=Column(DateTime(timezone=True)); pts_ms=Column(BigInteger,default=0); detection_type=Column(String(50)); bbox=Column(JSONB); confidence=Column(Float); track_id=Column(String(255)); global_track_id=Column(String(255)); plate_text=Column(String(100)); anomaly_score=Column(Float,default=0); embedding=Column(Vector(512)); det_metadata=Column("metadata",JSONB,default=dict); created_at=Column(DateTime(timezone=True),default=datetime.utcnow)

class CameraOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; stream_id:Optional[int]=None; camera_id:Optional[str]=None; name:str; location:str=""; lat:Optional[float]=None; lng:Optional[float]=None; hls_url:str=""; whep_url:str=""; stream_url:Optional[str]=None; rtsp_url:Optional[str]=None
    codec:Optional[str]=None; width:Optional[int]=None; height:Optional[int]=None; fps:Optional[float]=None; effective_codec:Optional[str]=None; effective_width:Optional[int]=None; effective_height:Optional[int]=None; effective_fps:Optional[float]=None
    status:str="active"; health_status:str="healthy"; connectivity_status:str="connected"; department:str="Traffic"; owner_organization:str="Gujarat Police"; camera_type:str="fixed"; protocol:str="rtsp"; source_system:str="cctv"; storage_type:str="local"; retention_days:Optional[int]=None
    analytics_capabilities:Any=None; maintenance_status:str="operational"; observed_at:Optional[datetime]=None; last_frame_at:Optional[datetime]=None; observed_source_fps:Optional[float]=None; observed_decode_fps:Optional[float]=None; observed_published_fps:Optional[float]=None
    external_id:Optional[str]=None; installation_date:Optional[date]=None; ptz_capable:bool=False; night_vision_capable:bool=False; coord_source:str="manual"; coord_confidence:Optional[float]=None; department_source:str="manual"; department_confidence:Optional[float]=None; vendor_id:Optional[uuid.UUID]=None; model_id:Optional[uuid.UUID]=None; processing_fps_category:str="pedestrian"; created_at:Optional[datetime]=None; updated_at:Optional[datetime]=None
    group_id:Optional[uuid.UUID]=None; zone:str="Ahmedabad Zone"; district:str="Ahmedabad"; subdivision:str="City Division"; police_station:str="City Police Station"

    @model_validator(mode="before")
    @classmethod
    def complete_playback_endpoints(cls, value):
        if value is None:
            return value
        stream_id = getattr(value, "stream_id", None)
        external_id = getattr(value, "external_id", None)
        if isinstance(value, dict):
            stream_id = value.get("stream_id")
            external_id = value.get("external_id")
            data = dict(value)
        else:
            data = {name: getattr(value, name, None) for name in cls.model_fields}
            data["stream_url"] = getattr(value, "stream_url", None)
            data["effective_codec"] = getattr(value, "effective_codec", None)
            data["effective_width"] = getattr(value, "effective_width", None)
            data["effective_height"] = getattr(value, "effective_height", None)
            data["effective_fps"] = getattr(value, "effective_fps", None)

        provider_id = None
        if external_id and re.fullmatch(r"cam\d{2}", str(external_id).strip(), re.IGNORECASE):
            provider_id = str(external_id).strip().lower()
        elif stream_id is not None:
            provider_id = f"cam{int(stream_id):02d}"

        if provider_id:
            rtsp_host = os.getenv("RTSP_HOST_IP", "103.250.160.189")
            playback_token = ""
            secret = (os.getenv("SECRET_KEY", "") or "").strip()
            if secret:
                try:
                    import jwt
                    playback_token = jwt.encode({"sub": "cctv-hls", "camera": provider_id, "exp": int(time.time()) + 300}, secret, algorithm="HS256")
                except Exception:
                    pass
            token_query = f"?access_token={playback_token}" if playback_token else ""
            if isinstance(value, dict):
                value["camera_id"]=provider_id
                value["hls_url"] = f"/api/cctv/{provider_id}/index.m3u8{token_query}"
            data["camera_id"] = provider_id
            data["hls_url"] = f"/api/cctv/{provider_id}/index.m3u8{token_query}"
            if not data.get("rtsp_url"):
                data["rtsp_url"] = f"rtsp://{rtsp_host}:8554/stream/{provider_id}"
            data["stream_url"] = data["rtsp_url"]
            if not data.get("whep_url"):
                data["whep_url"] = f"http://{rtsp_host}:8889/stream/{provider_id}/whep"
        return data

class CameraGroupOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID
    name:str
    code:str
    parent_id:Optional[uuid.UUID]=None
    group_type:str
    description:str=""
    total_cameras:int=0
    online_count:int=0
    degraded_count:int=0
    offline_count:int=0
    active_alerts_count:int=0
    children:list[Any]=Field(default_factory=list)

class CameraSearchResult(BaseModel):
    camera:CameraOut
    rank_score:float
    match_type:str

class CameraPage(BaseModel):
    items:list[CameraOut]
    total_count:int
    page:int
    page_size:int
    total_pages:int
    next_cursor:Optional[str]=None
    prev_cursor:Optional[str]=None
    summary:dict[str,Any]=Field(default_factory=dict)

class CameraCreate(BaseModel):
    stream_id:Optional[int]=Field(None,ge=1,le=30); name:str=Field(min_length=1,max_length=255); location:str=""; lat:Optional[float]=Field(None,ge=-90,le=90); lng:Optional[float]=Field(None,ge=-180,le=180); rtsp_url:Optional[str]=Field(None,max_length=512); hls_url:str=""; whep_url:str=""; department:str="Unassigned"; owner_organization:str="Unassigned"; camera_type:str="fixed"; protocol:str="rtsp"; source_system:str=""; external_id:Optional[str]=Field(None,max_length=255); storage_type:str=""; retention_days:Optional[int]=Field(None,ge=0); analytics_capabilities:list[str]=Field(default_factory=list); installation_date:Optional[date]=None; ptz_capable:bool=False; night_vision_capable:bool=False; coord_source:str="manual"; coord_confidence:Optional[float]=Field(1.0,ge=0,le=1); vendor_id:Optional[uuid.UUID]=None; model_id:Optional[uuid.UUID]=None; processing_fps_category:str=Field(default="pedestrian", pattern="^(highway|pedestrian|static)$")

    @field_validator("name")
    @classmethod
    def validate_camera_name(cls, v: str) -> str:
        if re.search(r"[<>]|javascript:|script", v, re.IGNORECASE):
            raise ValueError("Camera name contains invalid or unsafe characters")
        return v

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        from security_hardening import validate_rtsp_url
        try:
            return validate_rtsp_url(v)
        except ValueError as exc:
            raise ValueError(f"Invalid RTSP URL: {exc}") from exc

class PlateInvestigateRequest(BaseModel):
    plate: str = Field(..., min_length=2, max_length=64)

    @field_validator("plate")
    @classmethod
    def validate_plate(cls, v: str) -> str:
        cleaned = v.strip()
        if re.search(r"['\";\-\-/\*]", cleaned):
            raise ValueError("Invalid characters in license plate number")
        return cleaned


class AlertOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; cam_id:Optional[uuid.UUID]; alert_type:str; priority:str; entity_type:str; details:Any; acknowledged:bool; status:str; created_at:datetime; updated_at:datetime; acknowledged_at:Optional[datetime]; acknowledged_by:Optional[str]; resolved_at:Optional[datetime]; resolved_by:Optional[str]; closed_at:Optional[datetime]; closed_by:Optional[str]; confidence:Optional[float]=None
    cam_name:Optional[str]=None; camera_label:Optional[str]=None; severity:Optional[str]=None; human_summary:Optional[str]=None; camera:Any=None; detected_at:Optional[datetime]=None; detection_detail:Any=None; evidence:Any=None

class WatchlistOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; name:str; entity_type:str; description:str; plate_number:Optional[str]; alert_priority:str; is_active:bool; created_at:datetime

class WatchlistCreate(BaseModel):
    name:str; entity_type:str="person"; description:str=""; plate_number:Optional[str]=None; alert_priority:str="HIGH"
