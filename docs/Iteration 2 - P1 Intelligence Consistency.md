# Iteration 2 — P1 Intelligence Consistency

## Scope
P1 stabilizes the intelligence layer after P0 feed recovery without changing CCTV transport.

## Delivered
- One normalization contract in each service boundary (`1.1`), with identical uppercase/alphanumeric semantics and no OCR glyph guessing.
- Track-local ANPR evidence window with configurable production vote threshold and smaller isolated test threshold.
- Confirmed-only business sightings and journey promotion remain strict; raw/uncertain OCR stays diagnostic.
- Test session propagation for plate and person investigation requests; person investigation queries only session-scoped test tracks when a test session is active.
- Test face embeddings are persisted in the isolated `test_tracks.embedding` vector column.
- Watchlist reload is event-driven through Redis `watchlist:updated`, with periodic DB reload as a safety fallback.
- Alert deduplication uses Redis `SET NX EX` first and the durable database uniqueness constraint second; anomaly alerts deduplicate by camera + anomaly type rather than frame/detection id.
- Public-road behavior detection now learns a per-camera baseline, requires sustained deviation before alerting, and applies cooldown before another alert.
- P1 configuration is exposed through Docker Compose so thresholds are deploy-time configuration rather than code constants.
- P1 regression coverage is included in the existing three-check release workflow; no additional GitHub check is created.

## Production defaults
- `ANPR_VOTE_THRESHOLD=5`
- `ANPR_VOTE_WINDOW_FRAMES=12`
- `ANPR_OCR_INTERVAL_SECS=0.8`
- `ANPR_OCR_MIN_CONF=0.35`
- `WATCHLIST_RELOAD_SECS=60`
- `ALERT_COOLDOWN=60`
- `CROWD_BASELINE_ALPHA=0.04`
- `CROWD_DEVIATION_SIGMA=3.0`
- `CROWD_BASELINE_WARMUP_SECS=30`
- `CROWD_PERSISTENCE_SECS=5`
- `CROWD_COOLDOWN_SECS=60`

## Verification gate
Iteration 2 is complete only when the existing three CI checks are green and local Docker verification confirms:

```text
CCTV/RTSP             unaffected
ANPR normalization    consistent
ANPR confirmation     repeated exact evidence
Test isolation        no production leakage
Watchlist reload      event-driven + fallback
Alert dedup           Redis + DB durable
Crowd alerts          baseline + persistence + cooldown
P1 regression         PASS
```
