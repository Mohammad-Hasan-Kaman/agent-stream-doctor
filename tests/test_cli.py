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


def test_json_output(tmp_path, capsys):
    f = tmp_path / "s.txt"
    f.write_text("data: [DONE]\n\n", encoding="utf-8")  # done but zero chunks
    rc = main(["analyze", str(f), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, dict)
    assert "findings" in data and "stats" in data and "healthy" in data
