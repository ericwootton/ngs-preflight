FROM python:3.12-slim

LABEL org.opencontainers.image.title="ngs-preflight" \
      org.opencontainers.image.description="Pre-submission checks for NGS inputs (BED, sample sheet, reference, sample identity)" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . && rm -rf /build

# No USER line: the image runs as root, like the other images in WDL workflows. Cromwell saves inputs it downloads
# readable by its own user only, so a task running as another user cannot open them.
WORKDIR /data

# Mount your files at /data, and pass your own user so reports are not owned by root:
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/data" ngs-preflight:0.1.0 #       preflight check --bed targets.bed
ENTRYPOINT []
CMD ["preflight", "--help"]
