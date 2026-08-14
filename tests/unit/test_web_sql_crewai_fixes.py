"""Mock-based tests for the web/search, sql migration, dns, crewai wrappers,
and optimizer fixes.

Uses stdlib unittest.mock only (no new heavy dependencies).
"""

from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# 1. Web search: dead `"a"` branch + real results returned
# ---------------------------------------------------------------------------


def _make_fake_httpx(ddg_html: str):
    class _Resp:
        def __init__(self, text: str, status: int = 200) -> None:
            self.text = text
            self.status_code = status

        def json(self):
            return {}

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            return _Resp(ddg_html, 200)

        def get(self, url, **kwargs):
            return _Resp("", 200)

    return _Client


DDG_HTML = """
<html><body>
<a class="result__a" href="https://html.duckduckgo.com/l/?uddg=https%3A%2F%2Freal.example.com&rut=abc">Real Title</a>
<td class="result__snippet">A helpful snippet about the topic.</td>
</body></html>
"""


def test_web_search_returns_real_results():
    from sago.tools.web.search import WebSearchTool

    fake = _make_fake_httpx(DDG_HTML)
    with patch("httpx.Client", fake):
        res = WebSearchTool().run(query="python asyncio", max_results=5)
    assert isinstance(res, str)
    assert "Real Title" in res
    assert "real.example.com" in res
    assert "A helpful snippet" in res


def test_web_search_snippet_parser_ignores_dead_a_branch():
    from sago.tools.web.search import _DDGHTMLParser

    parser = _DDGHTMLParser(max_results=5)
    parser.feed(DDG_HTML)
    assert len(parser.results) == 1
    assert parser.results[0]["title"] == "Real Title"
    assert parser.results[0]["url"] == "https://real.example.com"
    assert "helpful snippet" in parser.results[0]["snippet"]


# ---------------------------------------------------------------------------
# 2. SQL migration: MySQL path fixed
# ---------------------------------------------------------------------------


def test_sql_migration_mysql_create_table():
    from sago.tools.database.sql_migration import SqlMigrationTool

    res = SqlMigrationTool().run(
        dialect="mysql",
        operation="create_table",
        table_name="users",
        details="email VARCHAR(255) NOT NULL",
    )
    assert "INT AUTO_INCREMENT PRIMARY KEY" in res
    # SQLite's invalid-for-MySQL syntax must NOT be emitted.
    assert "AUTOINCREMENT" not in res
    assert "INTEGER PRIMARY KEY" not in res


def test_sql_migration_postgres_still_intact():
    from sago.tools.database.sql_migration import SqlMigrationTool

    res = SqlMigrationTool().run(
        dialect="postgresql",
        operation="create_table",
        table_name="orders",
        details="user_id INT REFERENCES users(id)",
    )
    assert "SERIAL PRIMARY KEY" in res
    assert "DROP TABLE IF EXISTS orders" in res


# ---------------------------------------------------------------------------
# 3. DNS lookup: real lookup + structured + graceful errors
# ---------------------------------------------------------------------------


def test_dns_lookup_structured_output():
    from sago.tools.network.dns_lookup import DNSLookupTool

    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    def fake_gethostbyname_ex(host):
        return ("example.com", [], ["93.184.216.34"])

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "93.184.216.34\n", "")

    with (
        patch.object(sys.modules["socket"], "getaddrinfo", fake_getaddrinfo),
        patch.object(sys.modules["socket"], "gethostbyname_ex", fake_gethostbyname_ex),
        patch("subprocess.run", fake_run),
    ):
        res = DNSLookupTool().run(hostname="example.com", lookup_type="all")

    assert "=== DNS Lookup: example.com" in res
    assert "93.184.216.34" in res
    assert "A records" in res


def test_dns_lookup_gaierror_handled_gracefully():
    from sago.tools.network.dns_lookup import DNSLookupTool

    def boom(*args):
        raise socket.gaierror("Name or service not known")

    with (
        patch.object(sys.modules["socket"], "getaddrinfo", boom),
        patch.object(sys.modules["socket"], "gethostbyname_ex", boom),
        patch("subprocess.run", side_effect=FileNotFoundError()),
    ):
        res = DNSLookupTool().run(hostname="nope.invalid")

    assert isinstance(res, str)
    # Must not raise; should report the failure and still return a string.
    assert "failed" in res.lower()


# ---------------------------------------------------------------------------
# 4. CrewAI wrappers: CREWAI_TOOLS is usable (not a broken property)
# ---------------------------------------------------------------------------


def test_crewai_tools_proxy_is_dict_like():
    import sago.tools.crewai_wrappers as cw

    fake_registry = {"web_search": object(), "dns_lookup": object()}
    with patch.object(cw, "_get_registry", lambda: fake_registry):
        assert "web_search" in cw.CREWAI_TOOLS
        assert cw.CREWAI_TOOLS["web_search"] is fake_registry["web_search"]
        assert cw.CREWAI_TOOLS.get("missing") is None
        assert sorted(cw.CREWAI_TOOLS.keys()) == ["dns_lookup", "web_search"]
        assert set(cw.CREWAI_TOOLS) == {"web_search", "dns_lookup"}


def test_crewai_get_and_list_tools():
    import sago.tools.crewai_wrappers as cw

    fake_registry = {"web_search": "TOOL"}
    with patch.object(cw, "_get_registry", lambda: fake_registry):
        assert cw.get_crewai_tool("web_search") == "TOOL"
        assert cw.get_crewai_tool("nope") is None
        assert cw.list_crewai_tools() == ["web_search"]


# ---------------------------------------------------------------------------
# 5. Optimizer: dead branch removed (profiles without an injection point
#    are no longer silently counted as optimized)
# ---------------------------------------------------------------------------


def _write_profile(tmp_path: Path, with_system_prompt: bool) -> Path:
    p = tmp_path / "sample.py"
    body = (
        '"""Agent Profile: Sample\n\n'
        "Category: test\n"
        "Auto-generated.\n"
        '"""\n'
        "from dataclasses import dataclass\n\n"
        "@dataclass\n"
        "class AgentProfile:\n"
        "    name: str\n"
    )
    if with_system_prompt:
        body += (
            "\nPROFILE = AgentProfile(\n"
            '    name="sample",\n'
            '    system_prompt="""### Identity\n\nBe helpful.""",\n'
            ")\n"
        )
    else:
        body += '\nPROFILE = AgentProfile(\n    name="sample",\n)\n'
    p.write_text(body, encoding="utf-8")
    return p


def test_optimizer_injects_enterprise_guidelines():
    from sago.agents.optimizer import optimize_profile_file

    tmp = Path(tempfile.mkdtemp())
    profile = _write_profile(tmp, with_system_prompt=True)
    assert optimize_profile_file(profile) is True
    assert "Enterprise Execution Guidelines" in profile.read_text()


def test_optimizer_reports_unoptimizable_profile():
    import tempfile

    from sago.agents.optimizer import optimize_profile_file

    tmp = Path(tempfile.mkdtemp())
    profile = _write_profile(tmp, with_system_prompt=False)
    # No injection point -> must NOT be counted as optimized (dead branch fixed).
    assert optimize_profile_file(profile) is False
