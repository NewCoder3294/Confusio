"""Tests for the whitelist loader."""
import yaml

from defensive.bot.whitelist import load, lookup


class TestLoad:
    def test_loads_yaml(self, tmp_path):
        f = tmp_path / "wl.yaml"
        f.write_text(yaml.safe_dump({123: "OP-A", 456: "OP-B"}))
        result = load(f)
        assert result == {123: "OP-A", 456: "OP-B"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert load(tmp_path / "absent.yaml") == {}

    def test_int_keys(self, tmp_path):
        f = tmp_path / "wl.yaml"
        f.write_text("123: OP-A\n")
        assert load(f) == {123: "OP-A"}


class TestLookup:
    def test_hit(self):
        assert lookup(42, {42: "OP"}) == "OP"

    def test_miss(self):
        assert lookup(999, {42: "OP"}) is None
