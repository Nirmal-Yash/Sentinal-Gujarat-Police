# Sentinel AI Demo Test Data

Run `python test-data/generate_demo_videos.py` to create eight synthetic, loop-safe MP4 clips in `test-data/videos/`.

The clips are intentionally synthetic demo assets. They do not contain real government CCTV footage.

The manifest contains 30 Test camera slots rotating across the eight clips. The database seeder creates the isolated Test session, watchlist, lifecycle alerts, detections and journey tracks.

Seed the scenario from the repository root with:
```bash
python api/scripts/seed_demo_data.py
```

Use `--reset` for a fresh demonstration session. Use `--person-image /path/to/image.jpg` when a real demo face image is available to create the person watchlist embedding.
