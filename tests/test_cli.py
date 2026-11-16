"""Tests for the CLI (analyze path - no network needed)."""
import json

from agent_stream_doctor.cli import main


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


def test_json_output(tmp_path, capsys):
    f = tmp_path / "s.txt"
    f.write_text("data: [DONE]\n\n", encoding="utf-8")  # done but zero chunks
    rc = main(["analyze", str(f), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, dict)
    assert "findings" in data and "stats" in data and "healthy" in data
