"""
Patch for ingestion/worker.py:
After publishing to Redis stream, also set a snapshot key so the API
can serve camera previews to the dashboard.

This is imported and called from worker.py's _publish method.
"""
# Add to CameraWorker._publish() in worker.py:
#   self.r.set(f"snapshot:{self.cam_id}", frame_b64.encode(), ex=10)
#
# Already included in the patched worker below — no separate import needed.
