FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN --mount=type=secret,id=build_ca,target=/tmp/build-ca.pem \
    if [ -f /tmp/build-ca.pem ]; then export PIP_CERT=/tmp/build-ca.pem; fi; \
    pip install --no-cache-dir --require-hashes -r /app/backend/requirements.txt
RUN useradd --create-home --uid 10001 app
COPY --chown=app:app . /app
USER app
WORKDIR /app/backend
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
