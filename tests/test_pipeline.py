from pathlib import Path

import pytest

from mendacity.pipeline import AnalyzeOptions, analyze_image


def test_gemini_fixture_no_c2pa():
    root = Path(__file__).resolve().parents[1]
    img = root / "assets" / "Gemini_Generated_Image_tdi37ftdi37ftdi3-2636f904-cb97-48b0-85b9-80f95316b695.png"
    r = analyze_image(path=img, options=AnalyzeOptions())
    assert r["c2pa"]["status"] == "manifest_not_found"
    assert r["titan_watermark"]["status"] == "skipped"
    assert r["google_synthid"]["status"] == "skipped"
    assert r["meta"]["mime_inferred"] == "image/jpeg"


def test_second_fixture_mime_from_magic_bytes():
    root = Path(__file__).resolve().parents[1]
    img = root / "assets" / "19091bf8-6b96-436a-b014-3caa169accfd-15f9b822-abdc-41ff-8089-59d2da60bb26.png"
    r = analyze_image(path=img, options=AnalyzeOptions())
    # File is named .png but contains JPEG magic bytes (common export quirk).
    assert r["meta"]["mime_inferred"] == "image/jpeg"


def test_titan_rest_path(monkeypatch):
    import mendacity.titan as titan

    captured: dict = {}

    def fake_sigv4(url: str, body: bytes, region: str):
        captured["url"] = url
        captured["region"] = region
        return {"detectionResult": "NOT_GENERATED", "confidenceLevel": "HIGH"}

    monkeypatch.setattr(titan, "_sigv4_json_post", fake_sigv4)

    class FakeClient:
        def __getattr__(self, name):
            raise AttributeError(name)

    monkeypatch.setattr(titan.boto3, "client", lambda *a, **k: FakeClient())

    out = titan.detect_titan_watermark(b"\xff\xd8\xff", region="us-east-1")
    assert out["status"] == "ok"
    assert out["detectionResult"] == "NOT_GENERATED"
    assert "detectGeneratedContent" in captured["url"]
