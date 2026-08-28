FROM node:24.12.0-alpine3.23 AS workflow-checker

WORKDIR /checker
COPY system-contracts/workflow-dsl-2-candidate/package.json \
     system-contracts/workflow-dsl-2-candidate/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY system-contracts/workflow-dsl-2-candidate/generated ./generated

FROM python:3.14.2-alpine3.23 AS build

WORKDIR /workspace/evolution-system
RUN pip install --no-cache-dir uv==0.11.28
COPY evolution-system/pyproject.toml evolution-system/uv.lock evolution-system/README.md ./
COPY evolution-system/src ./src
RUN uv build --wheel --python 3.14 && \
    uv venv /opt/venv --python 3.14 && \
    uv pip install --python /opt/venv/bin/python dist/*.whl

FROM python:3.14.2-alpine3.23

WORKDIR /app
COPY --from=workflow-checker /usr/local/bin/node /usr/local/bin/node
COPY --from=workflow-checker /usr/lib/libstdc++.so.6 /usr/lib/libstdc++.so.6
COPY --from=workflow-checker /usr/lib/libgcc_s.so.1 /usr/lib/libgcc_s.so.1
COPY --from=workflow-checker /checker /opt/workflow-dsl
COPY --from=build /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    WSR_EVOLUTION_CONFIG=/run/config/evolution.json

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()" || exit 1
CMD ["python", "-m", "wsr_evolution"]
