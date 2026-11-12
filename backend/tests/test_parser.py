"""Opt-in real scanner/OCR tests. CI explicitly enables these; no parser mocks."""

import io
import os
import zipfile

import pytest
from docx import Document
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.ingest_worker import ProcessingError, process_once, sandbox
from app.private_storage import PrivateStorage
from tests.conftest import login
from tests.test_intake import target

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PARSER_TESTS") != "1",
    reason="Enable RUN_PARSER_TESTS=1 with the parser image/signatures",
)


def fixtures():
    stream = io.BytesIO()
    doc = Document()
    doc.add_heading("Synthetic heading", 1)
    doc.add_paragraph("Synthetic academic document.")
    doc.save(stream)
    docx = stream.getvalue()
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(40, 700, "Synthetic academic PDF evidence, not institutional policy.")
    pdf.save()
    digital = stream.getvalue()
    encrypted = io.BytesIO()
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(digital)))
    writer.encrypt("synthetic-fixture-password")
    writer.write(encrypted)
    image = Image.new("RGB", (1400, 400), "white")
    font = ImageFont.load_default(size=50)
    ImageDraw.Draw(image).text((50, 100), "SYNTHETIC STUDENT DOCUMENT", fill="black", font=font)
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawImage(ImageReader(image), 30, 400, width=540, height=154)
    pdf.save()
    scanned = stream.getvalue()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("../unsafe.xml", "synthetic")
    return {
        "digital.pdf": digital,
        "scanned.pdf": scanned,
        "encrypted.pdf": encrypted.getvalue(),
        "evidence.docx": docx,
        "unsafe.docx": archive.getvalue(),
        "malformed.pdf": b"%PDF-1.7\nMalformed synthetic fixture",
        "evidence.txt": b"Synthetic student text evidence",
        "evidence.md": b"# Synthetic heading\nSynthetic evidence",
    }


def test_real_scanner_and_format_extractors(settings, tmp_path):
    settings.private_storage_path = tmp_path / "objects"
    store = PrivateStorage(settings.private_storage_path)
    for name, data in fixtures().items():
        key = store.write(data)
        media = (
            "application/pdf"
            if name.endswith(".pdf")
            else (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if name.endswith(".docx")
                else "text/plain"
            )
        )
        if name == "encrypted.pdf":
            with pytest.raises(ProcessingError):
                sandbox(settings, key, media, "scan")
            continue
        sandbox(settings, key, media, "scan")
        if name in {"encrypted.pdf", "unsafe.docx", "malformed.pdf"}:
            with pytest.raises(ProcessingError):
                sandbox(settings, key, media, "extract")
        else:
            result = sandbox(settings, key, media, "extract")
            assert result["segments"]
            assert result["ocr"] == (name == "scanned.pdf")
            if name == "scanned.pdf":
                assert "SYNTHETIC" in result["segments"][0]["text"].upper()
            if name == "digital.pdf":
                assert result["segments"][0]["page"] == 1
            if name == "evidence.docx":
                assert result["segments"][1]["heading"] == "Synthetic heading"
    # The standard harmless anti-malware test signature, never executable malware.
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    with pytest.raises(ProcessingError, match="UNSAFE_FILE"):
        sandbox(settings, store.write(eicar), "text/plain", "scan")


def test_real_container_pipeline_commits_review_state(client, settings, tmp_path):
    from pydantic import SecretStr

    settings.private_storage_path = tmp_path / "objects"
    settings.ingest_database_url = SecretStr(
        "postgresql+psycopg://advisory_ingest:local-ingest-only@127.0.0.1:5432/advisory_test"
    )
    login(client, "advisor-a", True)
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    import json
    from uuid import uuid4

    result = client.post(
        "/api/v1/sources/uploads",
        data={"target": json.dumps(target())},
        files={"file": ("synthetic-scan.pdf", fixtures()["scanned.pdf"], "application/pdf")},
        headers={
            "Origin": "http://localhost:3000",
            "X-CSRF-Token": csrf,
            "If-Match": '"0"',
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert result.status_code == 201, result.text
    source = result.json()
    assert process_once(settings) == 1
    result = client.get("/api/v1/sources/" + source["id"])
    assert result.json()["state"] == "needs_review", result.text
    assert result.json()["ocr"]
    login(client)
    result = client.get(
        f"/api/v1/sources/{source['id']}/versions/{source['source_version_id']}/extraction"
    )
    assert result.status_code == 200, result.text
    assert "SYNTHETIC" in result.json()["segments"][0]["text"].upper()


def test_real_docx_expansion_limit(settings, tmp_path):
    settings.private_storage_path = tmp_path / "objects"
    store = PrivateStorage(settings.private_storage_path)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "A" * 100_000)
    with pytest.raises(ProcessingError, match="UNSAFE_ARCHIVE"):
        sandbox(
            settings,
            store.write(archive.getvalue()),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "extract",
        )
