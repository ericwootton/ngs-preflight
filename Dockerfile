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

RUN useradd --create-home --uid 10001 preflight
USER preflight
WORKDIR /data

# Mount your files at /data, for example:
#   docker run --rm -v "$PWD:/data" ngs-preflight:0.1.0 preflight check --bed targets.bed
ENTRYPOINT []
CMD ["preflight", "--help"]
