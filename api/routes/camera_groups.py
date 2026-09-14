"""Camera Hierarchy and Administrative Grouping Router.

Provides structured administrative hierarchy (State Command -> Zones -> Divisions -> Police Stations)
with real-time operational summaries (online, degraded, offline, active alerts) designed for 80,000+ cameras.
"""
from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_authenticated, require_permission, Principal
from database import get_db
from models import CameraGroupOut

router = APIRouter(prefix="/cameras/groups", tags=["camera-groups"], dependencies=[Depends(require_authenticated)])


@router.get("", response_model=list[CameraGroupOut])
@router.get("/", response_model=list[CameraGroupOut])
async def list_camera_groups(
    parent_id: Optional[uuid.UUID] = None,
    include_summary: bool = Query(True, description="Include live health and alert rollups"),
    tree: bool = Query(False, description="Return as hierarchical nested tree"),
    db: AsyncSession = Depends(get_db),
):
    """List administrative groups with live operational summaries."""
    query = """
        SELECT 
            g.id, g.name, g.code, g.parent_id, g.group_type, g.description,
            COALESCE(stats.total_cameras, 0) as total_cameras,
            COALESCE(stats.online_count, 0) as online_count,
            COALESCE(stats.degraded_count, 0) as degraded_count,
            COALESCE(stats.offline_count, 0) as offline_count,
            COALESCE(stats.active_alerts_count, 0) as active_alerts_count
        FROM camera_groups g
        LEFT JOIN (
            SELECT 
                c.group_id,
                COUNT(*) as total_cameras,
                COUNT(*) FILTER (WHERE c.health_status IN ('healthy', 'online') OR c.status = 'active') as online_count,
                COUNT(*) FILTER (WHERE c.health_status IN ('degraded', 'warning') OR c.status = 'reconnecting') as degraded_count,
                COUNT(*) FILTER (WHERE c.health_status IN ('offline', 'error') OR c.status = 'offline') as offline_count,
                (
                    SELECT COUNT(*) 
                    FROM alerts a 
                    WHERE a.cam_id IN (SELECT id FROM cameras sub_c WHERE sub_c.group_id = c.group_id AND sub_c.status <> 'deleted')
                      AND a.status = 'NEW' AND a.acknowledged = FALSE
                ) as active_alerts_count
            FROM cameras c
            WHERE c.status <> 'deleted'
            GROUP BY c.group_id
        ) stats ON stats.group_id = g.id
        ORDER BY g.group_type, g.name
    """
    rows = (await db.execute(text(query))).mappings().all()
    groups = [
        CameraGroupOut(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            parent_id=row["parent_id"],
            group_type=row["group_type"],
            description=row["description"] or "",
            total_cameras=int(row["total_cameras"] or 0),
            online_count=int(row["online_count"] or 0),
            degraded_count=int(row["degraded_count"] or 0),
            offline_count=int(row["offline_count"] or 0),
            active_alerts_count=int(row["active_alerts_count"] or 0),
            children=[],
        )
        for row in rows
    ]

    if not tree:
        if parent_id is not None:
            return [g for g in groups if g.parent_id == parent_id]
        return groups

    # Build hierarchical tree
    by_id = {g.id: g for g in groups}
    root_groups: list[CameraGroupOut] = []
    for g in groups:
        if g.parent_id and g.parent_id in by_id:
            by_id[g.parent_id].children.append(g)
        else:
            root_groups.append(g)

    return root_groups


@router.get("/{group_id}", response_model=CameraGroupOut)
async def get_camera_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get single group details with aggregated health statistics."""
    query = """
        SELECT 
            g.id, g.name, g.code, g.parent_id, g.group_type, g.description,
            COUNT(c.id) as total_cameras,
            COUNT(c.id) FILTER (WHERE c.health_status IN ('healthy', 'online') OR c.status = 'active') as online_count,
            COUNT(c.id) FILTER (WHERE c.health_status IN ('degraded', 'warning') OR c.status = 'reconnecting') as degraded_count,
            COUNT(c.id) FILTER (WHERE c.health_status IN ('offline', 'error') OR c.status = 'offline') as offline_count,
            (
                SELECT COUNT(*) 
                FROM alerts a 
                WHERE a.cam_id IN (SELECT id FROM cameras sub_c WHERE sub_c.group_id = g.id AND sub_c.status <> 'deleted')
                  AND a.status = 'NEW' AND a.acknowledged = FALSE
            ) as active_alerts_count
        FROM camera_groups g
        LEFT JOIN cameras c ON c.group_id = g.id AND c.status <> 'deleted'
        WHERE g.id = CAST(:id AS uuid)
        GROUP BY g.id, g.name, g.code, g.parent_id, g.group_type, g.description
    """
    row = (await db.execute(text(query), {"id": str(group_id)})).mappings().first()
    if not row:
        raise HTTPException(404, "Camera group not found")
    return CameraGroupOut(
        id=row["id"],
        name=row["name"],
        code=row["code"],
        parent_id=row["parent_id"],
        group_type=row["group_type"],
        description=row["description"] or "",
        total_cameras=int(row["total_cameras"] or 0),
        online_count=int(row["online_count"] or 0),
        degraded_count=int(row["degraded_count"] or 0),
        offline_count=int(row["offline_count"] or 0),
        active_alerts_count=int(row["active_alerts_count"] or 0),
        children=[],
    )
