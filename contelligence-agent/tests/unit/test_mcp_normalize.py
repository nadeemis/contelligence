"""Tests for SessionFactory._normalize_mcp_config."""

from app.core.session_factory import SessionFactory


class TestNormalizeMcpConfig:
    """Verify that MCP configs are normalised before being sent to the SDK."""

    def test_adds_tools_star_when_missing(self):
        servers = {
            "ms-learn": {"type": "http", "url": "https://learn.microsoft.com/api/mcp"},
        }
        result = SessionFactory._normalize_mcp_config(servers)
        assert result["ms-learn"]["tools"] == ["*"]
        assert result["ms-learn"]["url"] == "https://learn.microsoft.com/api/mcp"

    def test_preserves_existing_tools_field(self):
        servers = {
            "restricted": {"type": "http", "url": "https://example.com", "tools": ["tool_a"]},
        }
        result = SessionFactory._normalize_mcp_config(servers)
        assert result["restricted"]["tools"] == ["tool_a"]

    def test_preserves_empty_tools_list(self):
        """An explicit empty list means 'no tools' — don't override."""
        servers = {
            "none": {"type": "http", "url": "https://example.com", "tools": []},
        }
        result = SessionFactory._normalize_mcp_config(servers)
        assert result["none"]["tools"] == []

    def test_does_not_mutate_original(self):
        original_cfg = {"type": "http", "url": "https://example.com"}
        servers = {"srv": original_cfg}
        result = SessionFactory._normalize_mcp_config(servers)
        assert "tools" in result["srv"]
        assert "tools" not in original_cfg  # original untouched

    def test_multiple_servers(self):
        servers = {
            "a": {"type": "http", "url": "https://a.com"},
            "b": {"type": "stdio", "command": "node", "args": ["server.js"], "tools": ["only_this"]},
        }
        result = SessionFactory._normalize_mcp_config(servers)
        assert result["a"]["tools"] == ["*"]
        assert result["b"]["tools"] == ["only_this"]

    def test_empty_dict(self):
        assert SessionFactory._normalize_mcp_config({}) == {}
