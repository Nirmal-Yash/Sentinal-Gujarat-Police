"""Gujarat geodata for Test Mode virtual cameras."""

TEST_CAMERA_GEODATA = [
    {"lat": 23.2156, "lng": 72.6369, "location": "CH Road Junction, Gandhinagar", "department": "Traffic Control Unit", "camera_type": "fixed", "zone": "North Zone"},
    {"lat": 23.0338, "lng": 72.5072, "location": "SG Highway Flyover, Ahmedabad", "department": "City Surveillance Division", "camera_type": "anpr", "zone": "West Zone"},
    {"lat": 21.1702, "lng": 72.8311, "location": "Ring Road Toll Gate, Surat", "department": "Highway Patrol", "camera_type": "anpr", "zone": "South Zone"},
    {"lat": 22.3072, "lng": 73.1812, "location": "Express Highway Exit, Vadodara", "department": "Traffic Police", "camera_type": "fixed", "zone": "Central Zone"},
    {"lat": 22.3039, "lng": 70.8022, "location": "Kalawad Road, Rajkot", "department": "Urban Surveillance", "camera_type": "fixed", "zone": "Saurashtra Zone"},
    {"lat": 21.7645, "lng": 72.1519, "location": "Port Access Road, Bhavnagar", "department": "Port Security", "camera_type": "ptz", "zone": "Coastal Zone"},
    {"lat": 22.4707, "lng": 70.0577, "location": "Airport Junction, Jamnagar", "department": "City Police", "camera_type": "fixed", "zone": "West Zone"},
    {"lat": 23.5880, "lng": 72.3693, "location": "State Highway 41, Mehsana", "department": "Highway Division", "camera_type": "anpr", "zone": "North Zone"},
]


def test_geo_for_stream(stream_id: int, geo_index: int | None = None) -> dict:
    if geo_index is not None and 0 <= geo_index < len(TEST_CAMERA_GEODATA):
        return TEST_CAMERA_GEODATA[geo_index]
    idx = (max(1, int(stream_id)) - 1) % len(TEST_CAMERA_GEODATA)
    return TEST_CAMERA_GEODATA[idx]
