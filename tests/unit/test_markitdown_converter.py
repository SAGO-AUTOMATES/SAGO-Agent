"""Unit tests for MarkItDown converter and ConvertToMarkdownTool."""

import json
from pathlib import Path

from sago.tools.file.convert_to_markdown import ConvertToMarkdownTool
from sago.tools.file.read_file import ReadFileTool
from sago.utils.markitdown_converter import (
    convert_file_to_markdown,
    is_document_file,
    is_markitdown_available,
)


def test_is_document_file():
    assert is_document_file("report.pdf") is True
    assert is_document_file("presentation.pptx") is True
    assert is_document_file("sheet.xlsx") is True
    assert is_document_file("table.csv") is True
    assert is_document_file("index.html") is True
    assert is_document_file("main.py") is False
    assert is_document_file("script.sh") is False


def test_convert_csv_fallback(tmp_path: Path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("name,age,city\nAlice,30,New York\nBob,25,London\n", encoding="utf-8")

    success, md = convert_file_to_markdown(csv_file)
    assert success is True
    assert "| name | age | city |" in md
    assert "| Alice | 30 | New York |" in md


def test_convert_json_fallback(tmp_path: Path):
    json_file = tmp_path / "config.json"
    json_file.write_text(json.dumps({"service": "sago", "port": 8080}), encoding="utf-8")

    success, md = convert_file_to_markdown(json_file)
    assert success is True
    assert '"service": "sago"' in md

    # Also test explicit fallback function
    from sago.utils.markitdown_converter import _convert_with_fallback

    success_fb, md_fb = _convert_with_fallback(json_file, ".json")
    assert success_fb is True
    assert "```json" in md_fb


def test_convert_html_fallback(tmp_path: Path):
    html_file = tmp_path / "page.html"
    html_file.write_text(
        "<html><body><h1>Title</h1><p>Hello world paragraph</p></body></html>",
        encoding="utf-8",
    )

    success, md = convert_file_to_markdown(html_file)
    assert success is True
    assert "Title" in md
    assert "Hello world paragraph" in md


def test_convert_to_markdown_tool(tmp_path: Path):
    sample_file = tmp_path / "test.csv"
    sample_file.write_text("col1,col2\nval1,val2\n", encoding="utf-8")

    tool = ConvertToMarkdownTool()
    result = tool.run(file_path=str(sample_file))
    assert "| col1 | col2 |" in result

    # Test saving to output_path
    out_file = tmp_path / "output.md"
    result_save = tool.run(file_path=str(sample_file), output_path=str(out_file))
    assert "Successfully converted" in result_save
    assert out_file.exists()
    assert "| col1 | col2 |" in out_file.read_text(encoding="utf-8")


def test_read_file_tool_converts_documents(tmp_path: Path):
    sample_file = tmp_path / "data.csv"
    sample_file.write_text("item,price\nApple,1.50\nBanana,0.75\n", encoding="utf-8")

    tool = ReadFileTool()
    result = tool.run(file_path=str(sample_file))
    assert "converted to Markdown" in result
    assert "| item | price |" in result


def test_markitdown_available_check():
    # Should return bool without raising exception
    res = is_markitdown_available()
    assert isinstance(res, bool)
