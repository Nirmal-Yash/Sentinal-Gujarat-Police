"""Single canonical event envelope for every AI worker."""
import uuid

REQUIRED_FRAME_FIELDS = ("cam_id", "stream_id", "source_ts", "ingested_at", "pts_ms", "session_id")


def carry_frame_context(frame: dict) -> dict[bytes, bytes]:
    """Copy only transport-safe context from an ingestion frame event."""
    return {key.encode(): frame.get(key.encode(), b"") for key in REQUIRED_FRAME_FIELDS}


def detection_event(frame: dict, detection_type: str, **fields) -> dict[bytes, bytes]:
    event_id = str(uuid.uuid4()).encode()
    payload = {
        b"schema_version": b"1.0", b"event_id": event_id, b"detection_id": event_id,
        b"event_type": b"detection", b"detection_type": detection_type.encode(),
        **carry_frame_context(frame),
    }
    for key, value in fields.items():
        if value is not None:
            payload[key.encode()] = str(value).encode()
    return payload
