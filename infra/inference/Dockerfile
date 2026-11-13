FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY gateway.py /app/gateway.py
WORKDIR /app
USER 10001:10001
CMD ["uvicorn","gateway:app","--host","0.0.0.0","--port","8080","--no-access-log"]
