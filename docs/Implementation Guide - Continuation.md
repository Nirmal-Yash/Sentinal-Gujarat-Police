# Sentinel AI — Implementation Guide Continuation

## 0 — Document Boundary and Current Revision

This document is the **continuation** of the existing `docs/Implementation Guide.md`. It intentionally does **not** repeat the architecture, RBAC design, original test-mode design, vendor plan, PostGIS plan, or earlier implementation recommendations already documented there.

This continuation records only the material changes made **after the earlier guide**, based on the current `main` branch state and the concrete implementation commits through **2026-08-31**.

### Current revision anchor

The latest relevant UI revision is:

- `624a16dca274e1c00c7e28c8423b9bf9272c2f5c` — Remove metadata collapse control
- Parent: `0570ba2adf27c8b792590521000a2583504bef9b`
- `0570ba2adf27c8b792590521000a2583504bef9b` — Fix alerts workspace width
- `1c4f06d04f35e16d7ccb41ec2ea67638bb0b6093` — Warn on unknown registry columns
- `a126aed338b060529a26581616768edc05705edb` — Refine stream validation severity
- `1e1697730116bbee837bc5391de010642fbd6bbb` — Fix camera playback and collapsible metadata
- `81cab10b6d8d4e014923e9d062b55ec8e5f1e14a` — Refactor Camera Grid for Live Endpoints
- `497b17084a58c14b5b2016030b8963e5bc91f1cb` — Add collapsible metadata to monitor feed

The implementation has therefore moved beyond the older guide's planned onboarding/test/dashboard model into a materially richer live-feed and camera-registry state.

---

# 1 — Camera Feed System: Current Implemented Behaviour

The camera feed implementation was substantially refactored around a **source-selection and recovery model** rather than a single direct media URL.

## 1.1 Feed source selection

`dashboard/src/components/CameraGrid.jsx` now centralizes media selection through `playbackSources(cam)`.

### Production cameras

The normal feed path is:

```text
Camera record
    |
    +--> hls_url (preferred browser playback path)
    |
    +--> rtsp_url (fallback source)
    |
    +--> periodic snapshot endpoint (visual fallback)
```

The implementation prefers the registered HLS endpoint when one exists. When HLS fails or does not become usable, the player can move to the registered stream fallback. When no live path is available, the UI falls back to camera snapshots instead of leaving the card permanently blank.

A default HLS path is also synthesized from the camera identifier when no explicit HLS URL is present:

```text
https://cctv.corp8.cloud/cam{camera-id}/index.m3u8
```

The actual current source-selection logic should be treated as the source of truth; the older guide's generic endpoint examples are no longer the full picture.

## 1.2 Test-camera feed source handling

Test feeds use a different media mapping. When a test camera exposes a `/api/test/sessions/{session}/feeds/{feed}/video` URL, the dashboard derives the corresponding test HLS path:

```text
/test-hls/test/{session}/cam{feed}/index.m3u8
```

The same camera card therefore works for both production and test feeds without requiring a second visual component.

## 1.3 HLS playback engine

The feed uses `hls.js` when the browser supports Media Source Extensions.

The current player configuration emphasizes low-latency and recovery rather than uncontrolled buffering. Important settings include:

- `lowLatencyMode: true`
- bounded back-buffer
- bounded forward buffer
- live synchronization controls
- fragment retry controls
- manifest retry controls
- buffer-hole tolerance
- watchdog/recovery timing

The purpose is to keep the normal monitoring feed close to live while preventing a single fragment or manifest failure from permanently freezing the card.

## 1.4 Native HLS path

When `hls.js` is not required but the browser reports native HLS support, the player can assign the HLS URL directly to the `<video>` element and use normal media events.

## 1.5 HLS-to-stream fallback

The player includes a timed HLS fallback. If the HLS path does not become usable within the configured timeout, the implementation switches to the fallback media source when available.

The transition is explicit:

```text
HLS
  -> failed / timed out
      -> fallback stream
          -> failed
              -> snapshot / unavailable state
```

This prevents a feed from remaining in an indefinite spinner state.

## 1.6 Media error recovery

Fatal media errors are not handled as a simple terminal failure.

The current logic attempts:

```text
Fatal media error
    -> hls.recoverMediaError()

Fatal network error
    -> hls.startLoad()

Recovery still fails
    -> next playback source
```

This is complemented by `waiting` / `stalled` handling and a delayed recovery attempt.

## 1.7 Buffering state is now truthful

The monitoring card no longer shows a spinner simply because the player exists.

`buffering` is an explicit piece of state and is cleared when actual playback starts. The card therefore distinguishes between:

- waiting for a live feed,
- actively buffering,
- successfully playing,
- snapshot fallback,
- unavailable feed.

This is a UI correctness change, not only a cosmetic change.

## 1.8 Live state detection

`LivePlayer` calls `onLiveStatus(live)` and the camera card exposes a live indicator when real playback has started.

The visible status is therefore connected to player state rather than only the registry's nominal status value.

## 1.9 Snapshot fallback and refresh

When a live feed is not active, the card periodically requests the latest camera snapshot:

```text
GET /api/cameras/{camera_id}/snapshot?t={timestamp}
```

The timestamp query parameter prevents stale browser caching. Snapshot refresh is approximately every four seconds while the player is not live.

The snapshot is also used to keep the feed visually useful while the live path is initializing or recovering.

## 1.10 Dynamic stream aspect ratio

The feed no longer assumes every camera is 16:9.

`streamAspect(cam)` starts from registered/effective width and height and otherwise defaults to 16:9. Once actual media dimensions are available, the player reports the real aspect ratio using `videoWidth/videoHeight` or image natural dimensions.

That ratio is propagated to:

- camera cards,
- the fullscreen viewer,
- video/snapshot object-fit layout.

The result is reduced geometric distortion when cameras use different resolutions.

---

# 2 — Camera Card and Fullscreen Feed UX Changes

## 2.1 Camera card is now an operational feed surface

`CameraCard` now combines:

- camera identifier,
- live/offline state,
- alert count,
- feed rendering,
- metadata access,
- fullscreen feed action,
- map-location action.

The card remains primarily feed-first; metadata is deliberately not permanently displayed underneath every stream.

## 2.2 Grid density controls

The monitoring grid supports persisted column choices across:

```text
2 columns
3 columns
4 columns
5 columns
```

The selected value is saved in:

```text
localStorage key:
sentinel.camera-grid.columns.v1
```

The dashboard therefore restores the operator's preferred monitoring density after a reload.

## 2.3 Hover actions

The camera card keeps secondary controls visually quiet until the operator interacts with the feed.

The action region provides:

- fullscreen feed,
- locate on GIS map.

This reduces persistent overlay clutter across a multi-camera wall.

## 2.4 Fullscreen feed behaviour

The fullscreen viewer maintains the camera's actual stream aspect ratio and provides a dedicated header containing:

- camera identifier,
- camera name,
- alert count,
- metadata button,
- locate-on-map button,
- close button.

`Escape` closes the fullscreen viewer.

Plate/ANPR overlays are rendered over the live or snapshot image when detection metadata is available.

## 2.5 Fullscreen and card use the same playback abstraction

There is no separate player implementation for fullscreen mode. Both views reuse `LivePlayer`, which prevents the common situation where the tiled feed works but the enlarged feed follows a different stream/recovery path.

---

# 3 — Camera Metadata Interaction: Current Final Design

The feed metadata UX went through an intermediate collapsible implementation and has now been simplified.

## 3.1 Metadata entry point

Each monitoring card exposes a compact information control.

The operator opens metadata without leaving the feed wall.

The fullscreen viewer also exposes a metadata control.

## 3.2 Metadata dialog content

The metadata dialog currently presents:

| Field | Current display behaviour |
|---|---|
| Camera | Registry camera identifier such as `CAM-01` |
| Name | Registered camera name |
| Location | Registered location or explicit unavailable state |
| Department | Department / assignment |
| Owner | Owner organisation |
| Camera type | Camera type, with `Fixed` fallback |
| Status | Current health/status representation |
| Coordinates | Latitude + longitude when both are valid |
| Resolution | Effective width × height |
| Frame rate | Effective FPS |
| Codec | Effective/observed codec |
| Maintenance | Maintenance state when available |
| Last frame | Last observed frame timestamp |

The values are intentionally defensive: unavailable metadata is displayed explicitly rather than producing blank UI fragments.

## 3.3 Final interaction rule: close only

The requirement was subsequently simplified:

> Metadata should open fully expanded and should only have a close action.

The current `main.jsx` revision suppresses the collapse control in the metadata dialog using a global startup style rule, so the operator only sees the close control.

The current source still contains the earlier internal collapse state because the last change was intentionally kept minimal; however, the **visible product behaviour is close-only**.

This distinction matters for future refactoring: the behaviour is correct, but the dead collapse state/control implementation can be removed cleanly later.

## 3.4 Closing behaviour

The dialog closes through:

- explicit close button,
- `Escape`,
- clicking the overlay background.

Body scrolling is locked while the modal is open and restored on close.

---

# 4 — Intelligent Camera Registry Import: New Architecture

The camera registry import system is now split into two conceptual phases:

```text
FILE SELECTION
      |
      v
DRY-RUN INTELLIGENCE
      |
      +--> GREEN / READY
      |
      +--> AMBER / WARNING
      |
      +--> RED / BLOCKED
      |
      v
EXPLICIT IMPORT
```

The intelligence layer is implemented separately from the camera CRUD route so the decision logic is reusable and testable.

---

# 5 — File Parsing and Initial Safety Gate

`api/routes/camera_imports.py` owns parsing and orchestration.

## 5.1 Supported formats

Only these file extensions are accepted:

```text
.csv
.xlsx
```

Other file types produce an HTTP 415 response.

## 5.2 File size limit

The current registry import limit is:

```text
5 MiB
```

Oversized files produce HTTP 413.

## 5.3 CSV parser

CSV is decoded as UTF-8 with BOM support (`utf-8-sig`) and read through `csv.DictReader`.

The parser therefore expects the first row to represent the field headers.

## 5.4 XLSX parser

XLSX input is read using `openpyxl` in read-only/data-only mode.

The active worksheet's first row becomes the header row. Empty data rows are removed before analysis.

## 5.5 Empty-file rejection

A syntactically readable spreadsheet that contains no usable data rows is rejected before import.

This prevents an empty spreadsheet from becoming a nominally successful registry job.

---

# 6 — Intelligent Header Normalization

Headers are normalized using:

```text
trim
lowercase
spaces -> underscores
hyphens -> underscores
```

The intelligence layer also recognizes selected aliases.

Examples:

```text
camera_name   -> name
camera_id     -> external_id
id            -> external_id
latitude      -> lat
longitude     -> lng
lon           -> lng
owner         -> owner_organization
ownership     -> owner_organization
rtsp          -> rtsp_url
hls           -> hls_url
source        -> source_system
```

Recognized aliases are represented as warnings so the operator can see that normalization occurred.

### Important current-state note

The recent commit is titled **“Warn on unknown registry columns”**, but the present `normalize_headers()` implementation currently generates explicit notices for recognized aliases and does not yet emit a dedicated warning for every arbitrary unknown header. This should be treated as a known hardening item rather than assumed to be complete.

---

# 7 — Row Intelligence and Severity Model

Every data row is analyzed independently and returned with:

```text
row number
status
exact flag
issues[]
normalized payload
source field mapping
```

## 7.1 GREEN / READY

A row is green when:

- camera name is usable,
- at least one valid stream identity is present,
- stream fields are valid,
- optional supplied metadata can be preserved without warnings,
- no validation issue remains.

`exact = true` is returned for this clean state.

## 7.2 AMBER / WARNING

A row is warning-level when the camera remains usable but a non-critical field needs normalization or omission.

Examples include:

- malformed latitude,
- malformed longitude,
- only one coordinate supplied,
- invalid retention days,
- invalid installation date,
- invalid boolean metadata,
- malformed optional stream identifier when another valid stream path exists.

The warning is explicit and points to the affected row/field.

## 7.3 RED / BLOCKED

Critical problems prevent import of the row.

Most important example:

```text
name + no usable stream identity
```

The current required stream identity rule is:

```text
stream_id OR valid rtsp_url OR valid hls_url
```

If none of these is usable, the row is blocked.

A camera can therefore still be imported when one non-critical metadata value is bad, but it cannot be imported when the system cannot identify a usable camera stream.

---

# 8 — Stream Validation Severity Change

The stream validator was deliberately refined so that an invalid optional stream field is not automatically fatal when another usable stream identity exists.

### Example

```text
name      = CAM-12
stream_id = 1012
rtsp_url  = malformed
```

Current intelligence outcome:

```text
WARNING
RTSP URL is malformed; it will be ignored.
```

The row can still proceed because `stream_id` is usable.

In contrast:

```text
name      = CAM-12
stream_id = blank
rtsp_url  = blank
hls_url   = blank
```

produces:

```text
ERROR / BLOCKED
At least one usable stream identity is required.
```

This is the key business rule behind the requested “upload when the necessary data is present, but warn about inappropriate optional data” behaviour.

---

# 9 — Coordinate Intelligence

Coordinates are treated as important metadata but not as the minimum camera-stream identity requirement.

The parser accepts decimal coordinates and also attempts flexible coordinate parsing.

Bounds:

```text
Latitude : -90 .. +90
Longitude: -180 .. +180
```

### Warning examples

Invalid coordinate:

```text
Row 8 — lat
LAT is not a valid coordinate and will be ignored.
```

Incomplete pair:

```text
Row 9 — lat/lng
Latitude and longitude must be supplied together; incomplete coordinates will be ignored.
```

When both coordinates are valid, they are passed into the normalized camera payload.

When only one is valid, coordinates are intentionally omitted rather than storing an inconsistent spatial pair.

---

# 10 — Additional Optional-Field Intelligence

Current warning-aware normalization covers:

### Retention

`retention_days` must be a non-negative integer.

### Installation date

`installation_date` must parse as:

```text
YYYY-MM-DD
```

### Boolean capability fields

`ptz_capable` and `night_vision_capable` recognize values such as:

```text
true / false
1 / 0
yes / no
y / n
on / off
```

Invalid boolean text becomes a warning and is omitted so the database default can apply.

### Analytics capabilities

`analytics_capabilities` is split using `|` and converted into a usable list.

Example:

```text
person|vehicle|plate
```

becomes:

```text
["person", "vehicle", "plate"]
```

---

# 11 — Quality Summary Contract

The intelligence layer produces a file-level summary including:

```text
status
allow_upload
requires_warning_ack
total_rows
ready_rows
warning_rows
blocked_rows
exact_rows
warning_count
error_count
header_warnings
expected_fields
```

The aggregate file state is:

```text
blocked  -> any critical errors
warning  -> no critical errors, but warnings exist
ready    -> no errors and no warnings
```

This makes the UI deterministic: it is not estimating whether the import “looks okay”; it is consuming a structured quality contract.

---

# 12 — Dry-Run Validation API

New endpoint:

```http
POST /camera-imports/validate
```

Purpose:

- parse the file,
- analyze it,
- return the complete quality report,
- do not write camera records.

The public response deliberately excludes raw uploaded bytes.

This endpoint is now the correct first backend call after selecting a registry file.

---

# 13 — Explicit Import API

New endpoint:

```http
POST /camera-imports/import?acknowledge_warnings={true|false}
```

Rules:

### Clean file

```text
warning_count = 0
error_count   = 0
```

The file can proceed directly.

### Warning file

```text
warning_count > 0
error_count   = 0
```

The request must include:

```text
acknowledge_warnings=true
```

Otherwise the server returns HTTP 409 with the structured analysis so the UI can show exactly what needs review.

### Error file

Any critical validation error causes the server to return HTTP 422 and blocks the import.

---

# 14 — Import Write Path and Audit Behaviour

For an approved import, each analyzed row is normalized and then passed through the existing `CameraCreate` model validation.

The import path also applies:

- coordinate validation,
- vendor/model validation,
- duplicate lookup,
- camera creation/update semantics,
- audit log creation.

### Duplicate lookup precedence

The current route attempts identity matching through:

```text
stream_id
source_system + external_id
rtsp_url
```

where the relevant field is present.

An existing camera may therefore be updated instead of blindly inserting another registry row.

---

# 15 — Camera Coordinate Provenance Protection During Import

When updating an existing camera, the importer protects a high-confidence manually verified coordinate.

If an existing camera has:

```text
coord_source = manual
coord_confidence >= 0.9
```

the import path removes these fields from the update payload:

```text
lat
lng
coord_source
coord_confidence
```

This prevents a lower-confidence spreadsheet import from silently overwriting an operator-verified location.

---

# 16 — Camera Registry UI: Current User Journey

`dashboard/src/components/CameraRegistryModal.jsx` now implements the following import sequence:

```text
Camera Registry
   |
   +--> Bulk Import
          |
          +--> Select CSV/XLSX
          |
          +--> automatic validation request
          |
          +--> Quality Panel
          |
          +--> GREEN / AMBER / RED decision
          |
          +--> warning acknowledgement when needed
          |
          +--> import action
```

## 16.1 Automatic analysis on selection

Selecting a file immediately triggers:

```text
api.validateCameraImport(file)
```

The operator does not need to click a separate “Analyze” button.

## 16.2 Quality panel

The UI displays:

- overall quality state,
- total rows,
- clean rows,
- warning rows,
- blocked rows,
- individual issues.

Each issue is associated with:

```text
severity
row / header
field / column
message
```

Up to the first 30 issues are shown directly, with a count for the remainder.

## 16.3 Warning acknowledgement

When a file is uploadable but has warnings, the UI shows a confirmation checkbox:

> I reviewed the warnings and understand that the usable camera data will be imported while the listed non-critical fields are normalized or ignored.

Without that acknowledgement the final import button remains disabled.

## 16.4 Final button semantics

Current labels are intended to communicate the quality state:

```text
Clean file       -> Green-Flag & Import
Warning file     -> Acknowledge & Import
Blocked file     -> disabled
```

---

# 17 — Important End-to-End Import Wiring Gap

The current implementation contains both the new intelligent import API and the older camera import route.

This is important for future maintenance.

### New intelligent API exists

```text
POST /camera-imports/validate
POST /camera-imports/import
```

### Frontend validation is new and active

`CameraRegistryModal.jsx` calls:

```text
api.validateCameraImport(file)
```

### Current final-write bridge still uses the legacy path

`App.jsx` currently passes `importCameras` into the registry modal, and that bridge still calls:

```text
api.importCameras(file)
```

which maps to:

```text
POST /cameras/imports/csv
```

Therefore the current repository should be understood as:

```text
NEW intelligent dry-run
        |
        v
NEW quality UI
        |
        v
LEGACY final import bridge
```

The new `/camera-imports/import` endpoint is implemented, but the dashboard application has not yet been fully switched so that it is the only final-write route.

### Required hardening step

Update the App-level import callback so the acknowledged warning state is forwarded to:

```text
api.importCameraRegistry(file, acknowledgeWarnings)
```

Then make the old `/cameras/imports/csv` route either:

- a compatibility wrapper around the new intelligence path, or
- explicitly deprecated and removed after migration.

This is the most important outstanding integration item in the current camera-registry work.

---

# 18 — Alerts Page Layout Correction

The Alerts page had a visual sizing bug in which the alert workspace occupied only part of the available main content width, leaving a large empty region on the right.

## Root cause

The route container is a flex layout, and `AlertsPage` was not explicitly declaring itself as a horizontally expanding flex item.

## Fix

The page root now uses the equivalent of:

```text
width: 100%
flex: 1 1 auto
min-width: 0
```

and the internal alert workspace/content containers also use width/min-width-safe flex rules.

The result is that the alert table/panel consumes the available dashboard width beside the sidebar rather than shrinking to its content.

Commit:

```text
0570ba2adf27c8b792590521000a2583504bef9b
```

---

# 19 — Alert Page Current Behaviour Relevant to the Fix

The alert page remains a dedicated route and is rendered directly inside the main flex route area.

The current layout still includes:

- priority filter,
- lifecycle status filter,
- camera/ID search,
- plate search,
- from date,
- to date,
- refresh control,
- alert list/table,
- right-side investigation/detail drawer.

The main change in this continuation is not the alert domain model; it is the correction of the page's flex sizing so those existing controls have the full horizontal workspace available.

---

# 20 — Current Frontend Integration Map

At the present revision the most important dashboard relationships are:

```text
App.jsx
  |
  +--> CameraGrid.jsx
  |      |
  |      +--> CameraCard
  |      +--> LivePlayer
  |      +--> FullscreenModal
  |      +--> MetadataModal
  |
  +--> CameraRegistryModal.jsx
  |      |
  |      +--> api.validateCameraImport()
  |      +--> import callback from App.jsx
  |
  +--> AlertsPage.jsx
  |
  +--> MapView.jsx
  +--> InvestigationPanel.jsx
  +--> NotificationBell.jsx
```

The route shell continues to provide the topbar, sidebar, route switching and shared camera/alert state.

---

# 21 — Current Backend Integration Map

```text
FastAPI
  |
  +--> /camera-imports/validate
  |       |
  |       +--> file parser
  |       +--> header normalization
  |       +--> row intelligence
  |       +--> quality summary
  |
  +--> /camera-imports/import
  |       |
  |       +--> quality gate
  |       +--> warning acknowledgement
  |       +--> CameraCreate validation
  |       +--> vendor/model validation
  |       +--> duplicate lookup
  |       +--> camera create/update
  |       +--> camera audit log
  |
  +--> /cameras/* legacy/standard routes
  |
  +--> /alerts/*
  |
  +--> /operations/*
```

The intelligent import service is located at:

```text
api/services/camera_import_intelligence.py
```

The main orchestration route is:

```text
api/routes/camera_imports.py
```

---

# 22 — Current Tests Added for Registry Intelligence

`api/tests/test_camera_import_intelligence.py` currently covers the core decision model.

### Exact clean row

Verifies:

```text
status = ready
exact = true
allow_upload = true
requires_warning_ack = false
```

### Bad optional coordinate

Verifies:

```text
status = warning
allow_upload = true
requires_warning_ack = true
```

and confirms the issue points to `lat`.

### Missing stream identity

Verifies:

```text
status = blocked
allow_upload = false
```

and confirms the `MISSING_STREAM_IDENTITY` error is emitted.

---

# 23 — Current Known Technical Gaps to Carry Forward

These are the concrete items that should remain visible in the next implementation cycle.

## 23.1 Finish intelligent import end-to-end wiring

Switch `App.jsx` final import execution to the new `/camera-imports/import` route and forward the warning acknowledgement boolean.

## 23.2 Complete unknown-header warnings

The current intelligence layer recognizes aliases but does not yet generate a distinct warning for every arbitrary unknown column despite the intended requirement.

A robust final rule should classify each source column as:

```text
recognized exact
recognized alias
unknown / ignored
```

and expose that result to the UI.

## 23.3 Remove dead metadata collapse code

The visible collapse control is already suppressed, but `MetadataModal` still contains the old `collapsed` state and `CollapseIcon` path. The clean final implementation should delete that state and render the metadata body unconditionally.

## 23.4 Replace cosmetic suppression with component-level removal

The current close-only behaviour is enforced in `main.jsx` using a style rule targeted at the first header button in metadata dialogs. This works visually, but the preferred long-term implementation is to remove the obsolete collapse button/state from the component itself.

## 23.5 Run full application CI/runtime validation

The newly added registry tests exist, but the current connector-observable repository state does not provide evidence that the complete live application, Docker stack, and browser UI have all been executed together after the latest commits.

---

# 24 — Recommended Next-State Architecture

The desired final state should be:

```text
Camera Registry File
        |
        v
POST /camera-imports/validate
        |
        v
Quality Contract
        |
        +------ CLEAN ------> Green-Flag & Import
        |
        +---- WARNINGS -----> Review + Acknowledge
        |                         |
        |                         v
        |                    Acknowledge & Import
        |
        +------ ERRORS -----> Fix file / re-upload

All approved writes
        |
        v
POST /camera-imports/import
        |
        +--> CameraCreate validation
        +--> duplicate handling
        +--> provenance protection
        +--> audit log
        +--> camera registry
```

For live monitoring:

```text
Camera Registry
      |
      v
CameraGrid
      |
      +--> HLS
      |      |
      |      +--> recover
      |      +--> fallback
      |
      +--> fallback stream
      |
      +--> snapshot
      |
      +--> metadata dialog
      |
      +--> fullscreen feed
      |
      +--> GIS location
```

For operator experience:

```text
Monitor = feed-first
Metadata = on-demand
Alerts = full-width operational workspace
Registry import = explainable quality gate
```

---

# 25 — Exact Files Added or Materially Changed in This Continuation

### Backend

```text
api/services/camera_import_intelligence.py
api/routes/camera_imports.py
api/tests/test_camera_import_intelligence.py
```

### Dashboard

```text
dashboard/src/components/CameraGrid.jsx
dashboard/src/components/CameraRegistryModal.jsx
dashboard/src/components/AlertsPage.jsx
dashboard/src/api/client.js
dashboard/src/App.jsx
dashboard/src/main.jsx
dashboard/src/styles.css
```

The list above reflects the current code paths involved in the changes described in this document; not every file listed represents a net-new feature in the same commit.

---

# 26 — Revision Summary

The system has now moved from a basic camera registry/import concept toward an **operator-oriented, fault-tolerant feed and explainable registry workflow**.

The largest concrete changes since the previous guide are:

1. **Live camera playback was refactored into a resilient multi-source player** with HLS-first playback, recovery, fallback, snapshots, real live state and dynamic aspect ratio.
2. **Camera metadata became an on-demand modal** from both feed cards and fullscreen viewing; the final visible design is close-only.
3. **Camera registry import gained a structured intelligence layer** with file safety checks, row-level normalization, warning-vs-blocking semantics, coordinate intelligence, warning acknowledgement and a dry-run API.
4. **Alert workspace width was corrected** so the operational area fills the available desktop width.
5. **The current codebase has a clear next integration step:** route the UI's final registry write completely through the new intelligent import API and remove the legacy bridge once compatibility is no longer required.

This document should be treated as the handoff baseline for the next engineering iteration; the original `Implementation Guide.md` remains the historical architecture/planning document, while this continuation records the newer implemented state and the remaining integration hardening.