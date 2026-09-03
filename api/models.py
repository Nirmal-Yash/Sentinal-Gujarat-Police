import os, time, uuid, re
from datetime import datetime, date
from typing import Any, Optional
import jwt
from sqlalchemy import Column, String, Float, Boolean, DateTime, Date, Text, Integer, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict, Field, model_validator
from database import Base


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
    department_source=Column(String(32),default="unknown"); department_confidence=Column(Float); vendor_id=Column(UUID(as_uuid=True)); model_id=Column(UUID(as_uuid=True))
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
        """Canonical provider playback id: external_id cam01..cam30, then stream_id fallback."""
        external = (self.external_id or "").strip()
        if re.fullmatch(r"cam\d{2}", external, re.IGNORECASE):
            return external.lower()
        if self.stream_id is None:
            return None
        return f"cam{int(self.stream_id):02d}"
    @property
    def stream_url(self):
        if self.rtsp_url:
            return self.rtsp_url
        if self.stream_id is None:return None
        return f"rtsp://{os.getenv('RTSP_HOST_IP','103.250.160.189')}:8554/stream/cam{int(self.stream_id):02d}"

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
    id:uuid.UUID; stream_id:Optional[int]; name:str; location:str; lat:Optional[float]; lng:Optional[float]; hls_url:str; whep_url:str; stream_url:Optional[str]; rtsp_url:Optional[str]
    codec:Optional[str]; width:Optional[int]; height:Optional[int]; fps:Optional[float]; effective_codec:Optional[str]; effective_width:Optional[int]; effective_height:Optional[int]; effective_fps:Optional[float]
    status:str; health_status:str; connectivity_status:str; department:str; owner_organization:str; camera_type:str; protocol:str; source_system:str; storage_type:str; retention_days:Optional[int]
    analytics_capabilities:Any; maintenance_status:str; observed_at:Optional[datetime]; last_frame_at:Optional[datetime]; observed_source_fps:Optional[float]; observed_decode_fps:Optional[float]; observed_published_fps:Optional[float]
    external_id:Optional[str]; installation_date:Optional[date]; ptz_capable:bool; night_vision_capable:bool; coord_source:str; coord_confidence:Optional[float]; department_source:str; department_confidence:Optional[float]; vendor_id:Optional[uuid.UUID]; model_id:Optional[uuid.UUID]; created_at:datetime; updated_at:datetime

    @model_validator(mode="before")
    @classmethod
    def complete_playback_endpoints(cls, value):
        stream_id=getattr(value,"stream_id",None)
        external_id=getattr(value,"external_id",None)
        if isinstance(value,dict):
            stream_id=value.get("stream_id")
            external_id=value.get("external_id")
        provider_id=None
        if external_id and re.fullmatch(r"cam\d{2}", str(external_id).strip(), re.IGNORECASE):
            provider_id=str(external_id).strip().lower()
        elif stream_id is not None:
            provider_id=f"cam{int(stream_id):02d}"
        if provider_id:
            number=int(provider_id[3:])
            rtsp_host=os.getenv("RTSP_HOST_IP","103.250.160.189")
            if isinstance(value,dict): value=dict(value)
            else: value={name:getattr(value,name) for name in cls.model_fields if hasattr(value,name)}
            secret=(os.getenv("SECRET_KEY","") or "").strip()
            playback_token=""
            if secret:
                playback_token=jwt.encode({"sub":"cctv-hls","camera":provider_id,"exp":int(time.time())+300},secret,algorithm="HS256")
            token_query=f"?access_token={playback_token}" if playback_token else ""
            value["hls_url"]=f"/api/cctv/{provider_id}/index.m3u8{token_query}"
            if not value.get("rtsp_url"): value["rtsp_url"]=f"rtsp://{rtsp_host}:8554/stream/{provider_id}"
            value["stream_url"]=value["rtsp_url"]
            if not value.get("whep_url"): value["whep_url"]=f"http://{rtsp_host}:8889/stream/{provider_id}/whep"
        return value

class CameraCreate(BaseModel):
    stream_id:Optional[int]=Field(None,ge=0); name:str=Field(min_length=1,max_length=255); location:str=""; lat:Optional[float]=Field(None,ge=-90,le=90); lng:Optional[float]=Field(None,ge=-180,le=180); rtsp_url:Optional[str]=Field(None,max_length=512); hls_url:str=""; whep_url:str=""; department:str="Unassigned"; owner_organization:str="Unassigned"; camera_type:str="fixed"; protocol:str="rtsp"; source_system:str=""; external_id:Optional[str]=Field(None,max_length=255); storage_type:str=""; retention_days:Optional[int]=Field(None,ge=0); analytics_capabilities:list[str]=Field(default_factory=list); installation_date:Optional[date]=None; ptz_capable:bool=False; night_vision_capable:bool=False; coord_source:str="manual"; coord_confidence:Optional[float]=Field(1.0,ge=0,le=1); vendor_id:Optional[uuid.UUID]=None; model_id:Optional[uuid.UUID]=None

class AlertOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; cam_id:Optional[uuid.UUID]; alert_type:str; priority:str; entity_type:str; details:Any; acknowledged:bool; status:str; created_at:datetime; updated_at:datetime; acknowledged_at:Optional[datetime]; acknowledged_by:Optional[str]; resolved_at:Optional[datetime]; resolved_by:Optional[str]; closed_at:Optional[datetime]; closed_by:Optional[str]; confidence:Optional[float]=None
    cam_name:Optional[str]=None; camera_label:Optional[str]=None; severity:Optional[str]=None; human_summary:Optional[str]=None; camera:Any=None; detected_at:Optional[datetime]=None; detection_detail:Any=None; evidence:Any=None

class WatchlistOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; name:str; entity_type:str; description:str; plate_number:Optional[str]; alert_priority:str; is_active:bool; created_at:datetime

class WatchlistCreate(BaseModel):
    name:str; entity_type:str="person"; description:str=""; plate_number:Optional[str]=None; alert_priority:str="HIGH"
