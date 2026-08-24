FROM python:3.11-slim
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 --no-install-recommends && rm -rf /var/lib/apt/lists/*
RUN pip install opencv-python-headless numpy --no-cache-dir
WORKDIR /app
COPY generate_videos.py .
CMD ["python", "generate_videos.py"]
