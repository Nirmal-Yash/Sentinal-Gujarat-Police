def build_human_summary(alert_type: str, detection_data: dict, camera_name: str) -> str:
    plate = detection_data.get("plate_text") or detection_data.get("normalized_plate")
    if "watchlist" in str(alert_type).lower():
        return f"Watchlist target identified at {camera_name}. {('Plate: ' + plate) if plate else 'Person match detected'}."
    if "plate" in str(alert_type).lower():
        return f"Vehicle {plate or 'with an unreadable plate'} sighted at {camera_name}."
    if "running" in str(alert_type).lower():
        return f"Rapid movement detected at {camera_name}; possible running crowd incident."
    if "crowd" in str(alert_type).lower():
        return f"Unusual crowd activity detected at {camera_name}."
    if "person" in str(alert_type).lower() or "face" in str(alert_type).lower():
        return f"Person of interest identified at {camera_name}."
    return f"{str(alert_type or 'Alert').replace('_', ' ').capitalize()} at {camera_name}."
