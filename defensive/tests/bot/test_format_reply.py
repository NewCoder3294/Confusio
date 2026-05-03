"""Tests for the bot's reply formatter."""
from defensive.bot.telegram import _format_reply


class TestFormatReply:
    def test_authentic_verdict(self):
        body = {
            "artifact_id": "abc-123",
            "sha256": "4f3acafebabe1234567890abcdef0123456789abcdef0123456789abcdef0123",
            "verdict": {"level": "AUTHENTIC", "confidence": 0.92, "summary": "All clear."},
        }
        out = _format_reply(body)
        assert "AUTHENTIC" in out
        assert "0.92" in out
        assert "All clear." in out
        assert "abc-123" in out

    def test_too_large_error(self):
        body = {"_error": True, "status": 400,
                "body": {"detail": {"code": "image_too_large"}}}
        assert "10 MB" in _format_reply(body)

    def test_unsupported_mime(self):
        body = {"_error": True, "status": 400,
                "body": {"detail": {"code": "unsupported_mime"}}}
        assert "JPEG" in _format_reply(body)
