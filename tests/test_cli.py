"""Tests for the CLI (analyze path - no network needed)."""
import json
import sys
import types

import pytest

from agent_stream_doctor.cli import main


class _FakeResponse:
    """Minimal stand-in for a requests streaming response."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=8192):
        yield from self._chunks


@pytest.fixture
def fake_requests(monkeypatch):
    """Inject a stub `requests` module serving canned byte chunks."""
    module = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    module.RequestException = RequestException
    state = {"chunks": []}
    module.post = lambda *a, **k: _FakeResponse(state["chunks"])
    monkeypatch.setitem(sys.modules, "requests", module)
    return state


def test_analyze_healthy_file(tmp_path, capsys):
    f = tmp_path / "stream.txt"
    f.write_text(
        'data: {"choices":[{"delta":{"role":"assistant","content":"ok"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n",
        encoding="utf-8",
    )
    rc = main(["analyze", str(f)])
    assert rc == 0
    assert "HEALTHY" in capsys.readouterr().out


def test_analyze_broken_file_exit_code(tmp_path, capsys):
    f = tmp_path / "broken.txt"
    f.write_text('data: {"choices":[{"delta":{"reasoning_content":"hmm"}}]}\n\ndata: [DONE]\n\n', encoding="utf-8")
    rc = main(["analyze", str(f)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "reasoning-only-response" in out


def test_analyze_missing_file_is_a_clean_usage_error(capsys):
    rc = main(["analyze", "/definitely/not/a/real/file.txt"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Could not read" in err
    assert "Traceback" not in err


def test_analyze_directory_is_a_clean_usage_error(tmp_path, capsys):
    rc = main(["analyze", str(tmp_path)])
    assert rc == 2
    assert "Could not read" in capsys.readouterr().err


def test_record_with_missing_messages_file_is_clean(tmp_path, capsys):
    # Needs `requests` importable OR missing: either way the outcome
    # is a clean exit code 2, never a traceback. When requests is
    # absent the command stops at the import check, which is also 2.
    rc = main([
        "record",
        "--base-url", "https://example.invalid/v1/chat/completions",
        "--model", "m",
        "--messages-file", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "s.txt"),
    ])
    assert rc == 2
    assert "Traceback" not in capsys.readouterr().err


def test_record_captures_non_ascii_bytes_verbatim(tmp_path, capsys, fake_requests):
    """A byte-trickled UTF-8 stream (Persian text + emoji) must be
    saved byte-for-byte and diagnosed as the healthy stream it is.
    The old decode path guessed ISO-8859-1 when no charset was sent
    and wrote mojibake to disk, then reported phantom errors."""
    body = (
        'data: {"choices":[{"delta":{"role":"assistant","content":"سلام دنیا 😀"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    ).encode("utf-8")
    fake_requests["chunks"] = [bytes([b]) for b in body]  # 1 byte at a time
    out = tmp_path / "cap.txt"
    rc = main([
        "record",
        "--base-url", "http://stub.invalid/v1/chat/completions",
        "--model", "m",
        "--message", "hi",
        "--out", str(out),
    ])
    assert rc == 0
    assert "HEALTHY" in capsys.readouterr().out
    assert out.read_bytes() == body


def test_analyze_tolerates_invalid_utf8_bytes(tmp_path, capsys):
    """A capture with a few invalid UTF-8 bytes is diagnosed (the
    bytes become U+FFFD), not refused wholesale as 'unreadable' -
    `record` itself can legitimately save such a stream."""
    f = tmp_path / "bad-utf8.txt"
    f.write_bytes(
        b'data: {"choices":[{"delta":{"content":"ok\xff"}}]}\n\n'
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        b"data: [DONE]\n\n"
    )
    rc = main(["analyze", str(f)])
    assert rc in (0, 1)
    assert "Could not read" not in capsys.readouterr().err


def test_json_output(tmp_path, capsys):
    f = tmp_path / "s.txt"
    f.write_text("data: [DONE]\n\n", encoding="utf-8")  # done but zero chunks
    rc = main(["analyze", str(f), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, dict)
    assert "findings" in data and "stats" in data and "healthy" in data
