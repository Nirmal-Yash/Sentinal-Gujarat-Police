FROM pgvector/pgvector:pg16

# PostGIS keeps geometry as the spatial authority while retaining pgvector for
# the existing face re-identification workflow.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
