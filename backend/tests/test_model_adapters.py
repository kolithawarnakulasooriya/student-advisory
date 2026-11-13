"""Deterministic contract tests; actual Ollama acceptance is a separate gate."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.inference import InferenceError, ModelAdapter
from app.retrieval import selection_valid


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        [{}],
        {"disposition": [], "evidence_ids": [], "reason_code": "evidence"},
        {"disposition": "answered", "evidence_ids": ["FORGED"], "reason_code": "evidence"},
        {
            "disposition": "answered",
            "evidence_ids": ["E1"],
            "reason_code": "evidence",
            "claim": "invented",
        },
        {"disposition": "answered", "evidence_ids": [], "reason_code": "evidence"},
    ],
)
def test_malformed_or_forged_outputs_rejected(value):
    assert not selection_valid(value, [{"id": "E1", "text": "Synthetic requirement"}])


def test_vllm_private_contract(settings, monkeypatch):
    settings.inference_provider = "mock"
    adapter = ModelAdapter(settings)
    adapter.mock = False
    settings.inference_provider = "vllm"
    settings.vllm_token = SecretStr("synthetic-private-token")
    monkeypatch.setattr(adapter, "tokens", lambda role, value: 100)
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert str(request.url) == "http://127.0.0.1:8001/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-private-token"
        assert body["stream"] is False and body["max_tokens"] == 512
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "disposition": "answered",
                                    "evidence_ids": ["E1"],
                                    "reason_code": "evidence",
                                }
                            )
                        }
                    }
                ]
            },
        )

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    assert adapter.select("Synthetic question", [{"id": "E1", "text": "Synthetic evidence"}], [])[
        "evidence_ids"
    ] == ["E1"]
    assert len(seen) == 1


def test_dimensions_and_rerank_lengths_fail_closed(settings, monkeypatch):
    settings.inference_provider = "mock"
    adapter = ModelAdapter(settings)
    adapter.mock = False
    monkeypatch.setattr(
        adapter, "request", lambda *a, **k: {"embeddings": [[0.0] * 384], "scores": []}
    )
    with pytest.raises(InferenceError, match="DIMENSION"):
        adapter.embed(["Synthetic"])
    with pytest.raises(InferenceError, match="RERANK"):
        adapter.rerank("Question", ["Synthetic"])


def test_chunk_offsets_preserve_exact_text_and_bounds(settings):
    settings.inference_provider = "mock"
    adapter = ModelAdapter(settings)
    text = "Heading\n\n" + ("Synthetic paragraph with unicode café. " * 120)
    pieces = adapter.split(text)
    assert len(pieces) > 1 and pieces[0][0] == 0 and pieces[-1][1] == len(text.rstrip())
    for start, end, quote in pieces:
        assert text[start:end] == quote
        assert adapter.tokens("embedding", quote) <= 300
