FROM python:3.11-slim
RUN apt-get update && apt-get install -y libgomp1 --no-install-recommends && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ .
COPY scripts/seed_admin.py /app/seed_admin.py
COPY database/migrations /migrations

# Run one Uvicorn worker per container. FastAPI lifespan performs startup
# migrations/bootstrap checks, so multiple in-container workers duplicate
# initialization and can make the container unstable. Scale API horizontally
# with additional containers instead.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
