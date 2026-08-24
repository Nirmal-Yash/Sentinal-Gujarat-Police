FROM python:3.11-slim

# build-essential needed for packages that compile native extensions (faiss, insightface)
RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 libgomp1 build-essential \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only PyTorch FIRST with the PyTorch index to avoid downloading
# 2+ GB CUDA wheels. Must happen before requirements.txt to pin the build.
RUN pip install --no-cache-dir \
    torch==2.2.2+cpu \
    torchvision==0.17.2+cpu \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download model weights at image build time (not at first run)
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" && \
    python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

COPY *.py .
CMD ["python", "-u", "main.py"]
