FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY lumen/ lumen/

RUN pip install --no-cache-dir build && \
    python -m build --wheel --outdir /dist

# ---- runtime ----
FROM python:3.12-slim

RUN adduser --system --uid 1000 lumen

COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

USER lumen
WORKDIR /data

EXPOSE 8080

# Mount your config.toml at /config/config.toml, or override with LUMEN_CONFIG.
ENV LUMEN_CONFIG=/config/config.toml

ENTRYPOINT ["lumen-server"]
