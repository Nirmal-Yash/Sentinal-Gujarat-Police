CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── CAMERAS ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cameras (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    stream_id    INTEGER      UNIQUE,
    name         VARCHAR(255) NOT NULL,
    location     VARCHAR(255) DEFAULT '',
    lat          DOUBLE PRECISION,
    lng          DOUBLE PRECISION,
    rtsp_url     VARCHAR(512),
    hls_url      VARCHAR(512) DEFAULT '',
    whep_url     VARCHAR(512) DEFAULT '',
    codec        VARCHAR(20),
    width        INTEGER,
    height       INTEGER,
    fps          FLOAT,
    status       VARCHAR(50)  DEFAULT 'active',
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── WATCHLIST ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name           VARCHAR(255) NOT NULL,
    entity_type    VARCHAR(50)  NOT NULL DEFAULT 'person',
    description    TEXT         DEFAULT '',
    plate_number   VARCHAR(50),
    embedding      vector(512),
    alert_priority VARCHAR(20)  DEFAULT 'HIGH',
    is_active      BOOLEAN      DEFAULT TRUE,
    created_at     TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── DETECTIONS ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS detections (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cam_id           UUID REFERENCES cameras(id) ON DELETE SET NULL,
    timestamp        TIMESTAMPTZ NOT NULL,
    pts_ms           BIGINT      DEFAULT 0,
    detection_type   VARCHAR(50),
    bbox             JSONB,
    confidence       FLOAT,
    track_id         VARCHAR(255),
    global_track_id  VARCHAR(255),
    plate_text       VARCHAR(100),
    anomaly_score    FLOAT       DEFAULT 0,
    embedding        vector(512),
    metadata         JSONB       DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ─── ALERTS ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id     UUID,
    cam_id           UUID REFERENCES cameras(id) ON DELETE SET NULL,
    alert_type       VARCHAR(100) NOT NULL,
    priority         VARCHAR(20)  NOT NULL DEFAULT 'MEDIUM',
    confidence       FLOAT        DEFAULT 0.0,
    entity_type      VARCHAR(50)  DEFAULT 'unknown',
    details          JSONB        DEFAULT '{}',
    acknowledged     BOOLEAN      DEFAULT FALSE,
    acknowledged_at  TIMESTAMPTZ,
    acknowledged_by  VARCHAR(255),
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── GLOBAL TRACKS ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS global_tracks (
    id             VARCHAR(255) PRIMARY KEY,
    entity_type    VARCHAR(50),
    first_seen_cam UUID,
    last_seen_cam  UUID,
    first_seen_at  TIMESTAMPTZ,
    last_seen_at   TIMESTAMPTZ,
    cam_history    JSONB       DEFAULT '[]',
    embedding      vector(512),
    plate_text     VARCHAR(100),
    metadata       JSONB       DEFAULT '{}'
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_cam_stream    ON cameras(stream_id);
CREATE INDEX IF NOT EXISTS idx_cam_status    ON cameras(status);
CREATE INDEX IF NOT EXISTS idx_det_cam       ON detections(cam_id);
CREATE INDEX IF NOT EXISTS idx_det_ts        ON detections(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_det_track     ON detections(global_track_id);
CREATE INDEX IF NOT EXISTS idx_det_type      ON detections(detection_type);
CREATE INDEX IF NOT EXISTS idx_det_plate     ON detections(plate_text);
CREATE INDEX IF NOT EXISTS idx_alert_prio    ON alerts(priority);
CREATE INDEX IF NOT EXISTS idx_alert_ack     ON alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_alert_ts      ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_cam     ON alerts(cam_id);
CREATE INDEX IF NOT EXISTS idx_watch_active  ON watchlist(is_active);
CREATE INDEX IF NOT EXISTS idx_watch_plate   ON watchlist(plate_number);
CREATE INDEX IF NOT EXISTS idx_track_last    ON global_tracks(last_seen_at DESC);

-- Note: Cameras are NOT seeded here.
-- They are populated at runtime by ingestion/catalogue_sync.py
-- which calls http://live.corp8.cloud/api/ingest
-- Versioned schema evolution is owned exclusively by api/migrations.py.
-- This bootstrap file intentionally creates only the base tables/extensions
-- required for a fresh PostgreSQL volume; it must not include migrations.
