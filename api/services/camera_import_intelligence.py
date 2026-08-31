"""Explainable quality gate for camera registry CSV/XLSX imports."""
from __future__ import annotations
from datetime import date
from typing import Any
from urllib.parse import urlparse

CSV_ALIASES={"camera_id":"external_id","id":"external_id","camera_name":"name","camera":"name","latitude":"lat","longitude":"lng","lon":"lng","owner":"owner_organization","ownership":"owner_organization","rtsp":"rtsp_url","hls":"hls_url","source":"source_system"}
CORE_FIELDS={"name"}
STREAM_FIELDS={"stream_id","rtsp_url","hls_url"}
OPTIONAL_FIELDS={"location","department","owner_organization","lat","lng","source_system","external_id","storage_type","retention_days","analytics_capabilities","installation_date","ptz_capable","night_vision_capable","coord_source","coord_confidence","camera_type","protocol","vendor_id","model_id"}

def normalize_header(value:Any)->str:return str(value or "").strip().lower().replace(" ","_").replace("-","_")
def normalize_headers(headers:list[Any])->tuple[dict[str,str],list[dict[str,str]]]:
    mapping={};notices=[]
    for raw in headers:
        normalized=normalize_header(raw);target=CSV_ALIASES.get(normalized,normalized)
        if not normalized:continue
        mapping[str(raw)]=target
        if target!=normalized:notices.append({"code":"HEADER_ALIAS","severity":"warning","column":str(raw),"message":f"Column '{raw}' is recognized as '{target}'."})
    return mapping,notices

def parse_bool(value:Any)->bool:
    text=str(value).strip().lower()
    if text in {"true","1","yes","y","on"}:return True
    if text in {"false","0","no","n","off"}:return False
    raise ValueError("expected true/false")

def parse_coordinate(value:Any)->float:
    text=str(value).strip().upper().replace("°"," ").replace("'"," ").replace('"'," ");direction=-1 if text.endswith(("S","W")) else 1;text=text.rstrip("NSEW ");parts=[p for p in text.replace(","," ").split() if p];nums=[float(p) for p in parts]
    if not nums:raise ValueError("empty coordinate")
    return direction*(nums[0]+(nums[1]/60 if len(nums)>1 else 0)+(nums[2]/3600 if len(nums)>2 else 0))

def is_url(value:Any,schemes:set[str])->bool:
    try:
        p=urlparse(str(value).strip());return p.scheme.lower() in schemes and bool(p.netloc)
    except Exception:return False

def issue(code,severity,field,message,row):return {"code":code,"severity":severity,"field":field,"message":message,"row":row}

def analyze_row(row:dict[str,Any],row_number:int,header_mapping:dict[str,str])->dict[str,Any]:
    normalized={};source_fields={}
    for raw,value in row.items():
        target=header_mapping.get(str(raw),normalize_header(raw));normalized[target]=value;source_fields[target]=str(raw)
    issues=[];clean={}
    name=str(normalized.get("name") or "").strip()
    if not name:issues.append(issue("MISSING_NAME","error","name","Camera name is required.",row_number))
    else:clean["name"]=name
    stream_present=False
    for field in ("rtsp_url","hls_url"):
        value=str(normalized.get(field) or "").strip()
        if value:
            stream_present=True;schemes={"rtsp","rtsps"} if field=="rtsp_url" else {"http","https"}
            if not is_url(value,schemes):issues.append(issue("INVALID_STREAM_URL","error",field,f"{field} contains an invalid {field.replace('_url','').upper()} URL.",row_number))
            else:clean[field]=value
    raw_stream=normalized.get("stream_id")
    if raw_stream not in (None,""):
        stream_present=True
        try:
            value=int(str(raw_stream).strip())
            if value<0:raise ValueError
            clean["stream_id"]=value
        except (TypeError,ValueError):issues.append(issue("INVALID_STREAM_ID","error","stream_id","Stream ID must be a non-negative integer.",row_number))
    external=str(normalized.get("external_id") or "").strip()
    if external:clean["external_id"]=external
    if not stream_present:issues.append(issue("MISSING_STREAM_IDENTITY","error","stream_id/rtsp_url/hls_url","At least one usable stream identity is required: stream_id, RTSP URL, or HLS URL.",row_number))
    for field in ("location","department","owner_organization","source_system","storage_type","camera_type","protocol","coord_source"):
        value=str(normalized.get(field) or "").strip()
        if value:clean[field]=value
    coords={}
    for field in ("lat","lng"):
        value=str(normalized.get(field) or "").strip()
        if not value:continue
        try:
            parsed=parse_coordinate(value);lo,hi=(-90,90) if field=="lat" else (-180,180)
            if not lo<=parsed<=hi:raise ValueError
            coords[field]=parsed
        except (TypeError,ValueError):issues.append(issue("INVALID_COORDINATE","warning",field,f"{field.upper()} is not a valid coordinate and will be ignored.",row_number))
    if set(coords)=={"lat","lng"}:clean.update(coords)
    elif coords:issues.append(issue("INCOMPLETE_COORDINATES","warning","lat/lng","Latitude and longitude must be supplied together; incomplete coordinates will be ignored.",row_number))
    value=str(normalized.get("retention_days") or "").strip()
    if value:
        try:
            parsed=int(value)
            if parsed<0:raise ValueError
            clean["retention_days"]=parsed
        except (TypeError,ValueError):issues.append(issue("INVALID_INTEGER","warning","retention_days","Retention days must be a non-negative integer and will be ignored.",row_number))
    value=str(normalized.get("installation_date") or "").strip()
    if value:
        try:clean["installation_date"]=date.fromisoformat(value).isoformat()
        except ValueError:issues.append(issue("INVALID_DATE","warning","installation_date","Installation date must be YYYY-MM-DD and will be ignored.",row_number))
    for field in ("ptz_capable","night_vision_capable"):
        value=str(normalized.get(field) or "").strip()
        if value:
            try:clean[field]=parse_bool(value)
            except ValueError:issues.append(issue("INVALID_BOOLEAN","warning",field,f"{field} must be true/false and will use the system default.",row_number))
    capabilities=str(normalized.get("analytics_capabilities") or "").strip()
    if capabilities:clean["analytics_capabilities"]=[x.strip() for x in capabilities.split("|") if x.strip()]
    errors=[i for i in issues if i["severity"]=="error"]
    status="blocked" if errors else "warning" if issues else "ready"
    return {"row":row_number,"status":status,"exact":status=="ready","issues":issues,"normalized":clean,"source_fields":source_fields}

def summarize(rows,header_issues,expected_fields=None):
    errors=sum(sum(i["severity"]=="error" for i in r["issues"]) for r in rows);warnings=len(header_issues)+sum(sum(i["severity"]=="warning" for i in r["issues"]) for r in rows)
    return {"status":"blocked" if errors else "warning" if warnings else "ready","allow_upload":errors==0 and bool(rows),"requires_warning_ack":warnings>0,"total_rows":len(rows),"ready_rows":sum(r["status"]=="ready" for r in rows),"warning_rows":sum(r["status"]=="warning" for r in rows),"blocked_rows":sum(r["status"]=="blocked" for r in rows),"exact_rows":sum(r["exact"] for r in rows),"warning_count":warnings,"error_count":errors,"header_warnings":header_issues,"expected_fields":sorted(expected_fields or (CORE_FIELDS|STREAM_FIELDS|OPTIONAL_FIELDS))}
