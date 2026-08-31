from services.camera_import_intelligence import analyze_row, normalize_headers, summarize


def test_exact_registry_row_is_green():
    headers = ["name", "stream_id", "rtsp_url", "lat", "lng", "department"]
    mapping, header_issues = normalize_headers(headers)
    row = {"name": "Test Camera", "stream_id": "1001", "rtsp_url": "rtsp://10.0.0.1:554/stream1", "lat": "23.03", "lng": "72.58", "department": "Ahmedabad City Police"}
    result = analyze_row(row, 2, mapping)
    summary = summarize([result], header_issues)
    assert result["status"] == "ready"
    assert result["exact"] is True
    assert summary["status"] == "ready"
    assert summary["allow_upload"] is True
    assert summary["requires_warning_ack"] is False


def test_bad_optional_coordinate_is_warning_but_uploadable():
    headers = ["name", "stream_id", "rtsp_url", "lat", "lng"]
    mapping, header_issues = normalize_headers(headers)
    row = {"name": "Test Camera", "stream_id": "1002", "rtsp_url": "rtsp://10.0.0.2:554/stream1", "lat": "bad", "lng": "72.58"}
    result = analyze_row(row, 3, mapping)
    summary = summarize([result], header_issues)
    assert result["status"] == "warning"
    assert summary["allow_upload"] is True
    assert summary["requires_warning_ack"] is True
    assert any(i["field"] == "lat" for i in result["issues"])


def test_missing_stream_identity_blocks_import():
    headers = ["name", "location"]
    mapping, header_issues = normalize_headers(headers)
    row = {"name": "Unusable Camera", "location": "Ahmedabad"}
    result = analyze_row(row, 4, mapping)
    summary = summarize([result], header_issues)
    assert result["status"] == "blocked"
    assert summary["allow_upload"] is False
    assert any(i["code"] == "MISSING_STREAM_IDENTITY" for i in result["issues"])
