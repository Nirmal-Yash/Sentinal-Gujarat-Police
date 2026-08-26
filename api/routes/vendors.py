"""Normalized vendor/model registry; deliberately separate from camera facts."""
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from auth import Principal, require_role
from database import get_db

router = APIRouter(prefix="/vendors", tags=["vendors"])

class VendorInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(None, max_length=255)
    contact_email: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=64)
    support_url: str | None = Field(None, max_length=512)
    protocol_support: list[str] = ["RTSP"]
    active: bool = True

class ModelInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    camera_type: str = "fixed"
    default_codec: str | None = None
    default_width: int | None = Field(None, ge=1)
    default_height: int | None = Field(None, ge=1)
    default_fps: float | None = Field(None, ge=0)
    analytics_capabilities: list[str] = []

def _protocols(protocols: list[str]) -> list[str]:
    values = [item.upper() for item in protocols]
    if not values or any(item not in {"RTSP", "ONVIF"} for item in values):
        raise HTTPException(422, "Only RTSP and ONVIF vendor protocols are supported")
    return sorted(set(values))

@router.get("/")
async def list_vendors(_: Principal = Depends(require_role("OPERATOR")), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("SELECT * FROM vendors ORDER BY active DESC, name"))
    return [dict(row) for row in rows.mappings()]

@router.post("/", status_code=201)
async def create_vendor(body: VendorInput, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    try:
        row = (await db.execute(text("""INSERT INTO vendors(name,contact_name,contact_email,contact_phone,support_url,protocol_support,active)
          VALUES(:name,:contact_name,:contact_email,:contact_phone,:support_url,:protocol_support,:active) RETURNING *"""),
          {**body.model_dump(), "protocol_support": _protocols(body.protocol_support)})).mappings().one()
        await db.commit(); return dict(row)
    except IntegrityError as exc:
        await db.rollback(); raise HTTPException(409, "Vendor already exists") from exc

@router.put("/{vendor_id}")
async def update_vendor(vendor_id: uuid.UUID, body: VendorInput, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    values = {**body.model_dump(), "protocol_support": _protocols(body.protocol_support), "id": str(vendor_id)}
    row = (await db.execute(text("""UPDATE vendors SET name=:name,contact_name=:contact_name,contact_email=:contact_email,
      contact_phone=:contact_phone,support_url=:support_url,protocol_support=:protocol_support,active=:active,updated_at=NOW()
      WHERE id=CAST(:id AS uuid) RETURNING *"""), values)).mappings().first()
    if not row: raise HTTPException(404, "Vendor not found")
    await db.commit(); return dict(row)

@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: uuid.UUID, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("DELETE FROM vendors WHERE id=CAST(:id AS uuid)"), {"id": str(vendor_id)})
    if not result.rowcount: raise HTTPException(404, "Vendor not found")
    await db.commit(); return {"status": "deleted"}

@router.get("/{vendor_id}/models")
async def list_models(vendor_id: uuid.UUID, _: Principal = Depends(require_role("OPERATOR")), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("SELECT * FROM camera_models WHERE vendor_id=CAST(:id AS uuid) ORDER BY name"), {"id": str(vendor_id)})
    return [dict(row) for row in rows.mappings()]

@router.post("/{vendor_id}/models", status_code=201)
async def create_model(vendor_id: uuid.UUID, body: ModelInput, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    try:
        row = (await db.execute(text("""INSERT INTO camera_models(vendor_id,name,camera_type,default_codec,default_width,default_height,default_fps,analytics_capabilities)
          VALUES(CAST(:vendor_id AS uuid),:name,:camera_type,:default_codec,:default_width,:default_height,:default_fps,CAST(:analytics_capabilities AS jsonb)) RETURNING *"""),
          {"vendor_id": str(vendor_id), **body.model_dump(), "analytics_capabilities": __import__('json').dumps(body.analytics_capabilities)})).mappings().one()
        await db.commit(); return dict(row)
    except IntegrityError as exc:
        await db.rollback(); raise HTTPException(409, "Vendor or model already exists") from exc
