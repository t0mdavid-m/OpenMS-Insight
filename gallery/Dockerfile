# OpenMS-Insight example gallery.
#
# Build from the repository root:
#     docker build -f gallery/Dockerfile -t openms-insight-gallery .
#
# The example dataset is committed under gallery/data/ and copied in with the source,
# so the build fetches no data and works offline.

# --- Stage 1: build the Vue bundle -------------------------------------------------
FROM node:20-bookworm-slim AS vue

WORKDIR /build
COPY js-component/package.json js-component/package-lock.json ./js-component/
RUN cd js-component && npm ci

COPY js-component ./js-component
RUN cd js-component && npm run build


# --- Stage 2: runtime --------------------------------------------------------------
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Components cache Parquet relative to the working directory; keep that on a
    # writable path rather than in the read-only application tree.
    GALLERY_CACHE_DIR=/var/cache/gallery \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY gallery/requirements.txt /app/gallery/requirements.txt
RUN pip install --no-cache-dir -r /app/gallery/requirements.txt

# The package's build backend force-includes the built bundle, so it must be in place
# before the package is installed.
#
# .gitignore is copied deliberately, not by accident: hatchling honours it when
# selecting files, and it excludes openms_insight/js-component/. Without it the wheel
# build fails, because `packages = ["openms_insight"]` sweeps the bundle in once and
# `force-include` adds it a second time at the same archive path.
COPY pyproject.toml README.md LICENSE .gitignore /app/
COPY openms_insight /app/openms_insight
COPY --from=vue /build/js-component/dist /app/openms_insight/js-component/dist
RUN pip install --no-cache-dir --no-deps /app

COPY gallery /app/gallery

RUN useradd --create-home --uid 10001 gallery \
    && mkdir -p "$GALLERY_CACHE_DIR" \
    && chown -R gallery:gallery "$GALLERY_CACHE_DIR"
USER gallery

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["streamlit", "run", "gallery/app.py"]
