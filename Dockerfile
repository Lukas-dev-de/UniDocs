# UniDocs server: self-hosted web app + sync API.
#
#   docker build -t unidocs-server .
#   docker run -p 8550:8550 -v unidocs-data:/data unidocs-server
#
# Documents live in /data (UNIDOCS_DATA_DIR). The API token is generated on
# first start and printed to the log; pin it with UNIDOCS_API_TOKEN.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UNIDOCS_DATA_DIR=/data

WORKDIR /app

# Copy only what the server needs, then install the web deps.
COPY pyproject.toml README.md ./
COPY src ./src
COPY tools ./tools

RUN pip install --no-cache-dir '.[web]'

EXPOSE 8550

CMD ["python", "tools/serve_web.py", "--host", "0.0.0.0", "--port", "8550"]
