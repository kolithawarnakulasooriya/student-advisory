FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f
RUN apt-get update && apt-get install -y --no-install-recommends \
    clamav clamav-freshclam poppler-utils tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pypdf==7.0.1 python-docx==1.2.0 lxml==6.1.3 typing_extensions==4.16.0
COPY extract.py /opt/advisory/extract.py
USER 10001:10001
ENTRYPOINT ["python", "/opt/advisory/extract.py"]
