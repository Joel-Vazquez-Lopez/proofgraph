FROM node:22-bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-venv python3-pip ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps/web/package*.json apps/web/
RUN cd apps/web && npm ci

COPY apps/api/requirements.txt apps/api/
RUN python3 -m venv /opt/proofgraph-venv && \
    /opt/proofgraph-venv/bin/pip install --no-cache-dir -r apps/api/requirements.txt

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV PROOFGRAPH_API_PORT=8000

RUN cd apps/web && npm run build

RUN chmod +x deploy/huggingface/start.sh

EXPOSE 7860

CMD ["./deploy/huggingface/start.sh"]
