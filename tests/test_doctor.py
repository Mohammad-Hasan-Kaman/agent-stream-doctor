"""Tests for every diagnostic check, one per failure class."""
import json

from agent_stream_doctor.doctor import diagnose
from agent_stream_doctor.models import Severity
from tests import streams


def ids(report):
    return {f.check_id for f in report.findings}


def test_healthy_stream_passes():
    report = diagnose(streams.HEALTHY)
    assert report.healthy, [f.to_dict() for f in report.findings]
    assert report.stats["content_chars"] == len("Hello world")
    assert report.stats["finish_reasons"] == ["stop"]


def test_empty_stream_detected():
    report = diagnose(streams.EMPTY_STREAM)
    assert "empty-stream" in ids(report)
    assert not report.healthy


def test_reasoning_only_response_detected():
    """The exact failure class from hermes-agent#92803."""
    report = diagnose(streams.REASONING_ONLY)
    found = ids(report)
    assert "reasoning-only-response" in found
    f = next(f for f in report.findings if f.check_id == "reasoning-only-response")
    assert "reasoning" in f.message.lower()
    assert report.stats["reasoning_chars"] > 0
    assert report.stats["content_chars"] == 0


def test_missing_finish_reason_detected():
    report = diagnose(streams.MISSING_FINISH_REASON)
    assert "missing-finish-reason" in ids(report)


def test_malformed_sse_detected():
    report = diagnose(streams.MALFORMED_SSE)
    assert "malformed-sse-line" in ids(report)
    finding = next(f for f in report.findings if f.check_id == "malformed-sse-line")
    assert finding.evidence  # shows the offending line


def test_invalid_json_payload_detected():
    report = diagnose(streams.INVALID_JSON)
    assert "invalid-json-payload" in ids(report)


def test_data_after_done_detected_as_warning():
    report = diagnose(streams.DATA_AFTER_DONE)
    assert "data-after-done" in ids(report)
    f = next(f for f in report.findings if f.check_id == "data-after-done")
    assert f.severity is Severity.WARNING


def test_no_done_sentinel_warned():
    report = diagnose(streams.NO_DONE_SENTINEL)
    # ends without finish_reason AND without [DONE]
    found = ids(report)
    assert "missing-finish-reason" in found
    assert "stream-ended-without-done" in found


def test_truncated_tool_call_detected():
    report = diagnose(streams.TOOL_CALL_TRUNCATED)
    found = ids(report)
    assert "incomplete-tool-call" in found
    assert "unparseable-tool-arguments" in found


def test_complete_tool_call_passes():
    report = diagnose(streams.TOOL_CALL_COMPLETE)
    tool_findings = [
        f for f in report.findings
        if f.check_id in ("incomplete-tool-call", "unparseable-tool-arguments")
    ]
    assert not tool_findings, [f.to_dict() for f in report.findings]


def test_empty_content_stream_flagged():
    report = diagnose(streams.EMPTY_CONTENT)
    assert "empty-content-stream" in ids(report)


def test_report_serializes_to_json():
    report = diagnose(streams.REASONING_ONLY)
    data = json.loads(json.dumps(report.to_dict()))
    assert data["healthy"] is False
    assert any(f["check_id"] == "reasoning-only-response" for f in data["findings"])


def test_every_finding_has_explanation():
    report = diagnose(streams.TOOL_CALL_TRUNCATED)
    report2 = diagnose(streams.HEALTHY)
    for f in report.findings + report2.findings:
        assert f.explanation, f"missing explanation for {f.check_id}"
