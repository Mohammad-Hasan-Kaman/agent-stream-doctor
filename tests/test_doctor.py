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


def test_malformed_chunk_shapes_do_not_crash():
    """Valid JSON with the wrong shape must become findings, not
    exceptions - the tool exists for broken streams."""
    broken_streams = [
        'data: {"choices":[{"delta":"oops"}]}\n\ndata: [DONE]\n\n',
        'data: {"choices":"nope"}\n\ndata: [DONE]\n\n',
        'data: {"choices":[42]}\n\ndata: [DONE]\n\n',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":null}]}}]}\n\ndata: [DONE]\n\n',
        'data: {"choices":[{"delta":{"content":123}}]}\n\ndata: [DONE]\n\n',
    ]
    for text in broken_streams:
        report = diagnose(text)  # must not raise
        assert isinstance(report.findings, list)


def test_data_after_single_done_detected():
    """Chunks after one [DONE] (and no second one) are still lost
    chunks - the check is about position, not sentinel count."""
    text = (
        'data: {"choices":[{"delta":{"role":"assistant","content":"Hi"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
        'data: {"choices":[{"delta":{"content":"ghost"}}]}\n\n'
    )
    report = diagnose(text)
    assert "data-after-done" in ids(report)


def test_complete_tool_call_stream_is_healthy():
    """A pure tool-call response has no text content by design; it
    must not be flagged as an empty-content stream."""
    report = diagnose(streams.TOOL_CALL_COMPLETE)
    assert report.healthy, [f.to_dict() for f in report.findings]


def test_lone_done_sentinel_is_an_empty_stream():
    report = diagnose("data: [DONE]\n\n")
    assert "empty-stream" in ids(report)
    assert not report.healthy


def test_non_object_payload_flagged():
    """A payload that parses as JSON but is not an object (e.g. a
    double-encoded response) is not a usable chunk."""
    report = diagnose('data: 42\n\ndata: "text"\n\ndata: [DONE]\n\n')
    assert "invalid-json-payload" in ids(report)
    assert not report.healthy


def test_content_as_list_of_parts_is_counted():
    text = (
        'data: {"choices":[{"delta":{"role":"assistant",'
        '"content":[{"type":"text","text":"Hello"}]}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    report = diagnose(text)
    assert report.stats["content_chars"] == len("Hello")
    assert report.healthy, [f.to_dict() for f in report.findings]


def test_bom_prefixed_stream_is_healthy():
    report = diagnose("\ufeff" + streams.HEALTHY)
    assert report.healthy, [f.to_dict() for f in report.findings]
    assert report.stats["content_chars"] == len("Hello world")


def test_multiline_data_payload_diagnosed_as_content():
    text = (
        'data: {"choices":[{"delta":{"role":"assistant",\n'
        'data: "content":"Hi"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    report = diagnose(text)
    assert "invalid-json-payload" not in ids(report)
    assert report.stats["content_chars"] == len("Hi")


def test_non_string_finish_reason_does_not_crash():
    """A router emitting finish_reason as an object, list, number or
    bool produces a malformed chunk, not a TypeError. None of these
    count as a termination, so missing-finish-reason must fire."""
    for fr in ('{"a":1}', '["stop"]', "123", "true", "NaN"):
        chunk = (
            '{"choices":[{"delta":{"role":"assistant","content":"x"},'
            f'"finish_reason":{fr}' + "}]}"
        )
        text = f"data: {chunk}\n\ndata: [DONE]\n\n"
        report = diagnose(text)  # must not raise
        assert "missing-finish-reason" in ids(report), fr


def test_mixed_type_finish_reasons_do_not_crash():
    """One string and one numeric finish_reason: the numeric one is
    ignored, the string terminates the choice - no crash in sorted()."""
    text = (
        'data: {"choices":[{"delta":{"content":"x"},"finish_reason":123}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    report = diagnose(text)
    assert report.stats["finish_reasons"] == ["stop"]


def test_unhashable_tool_call_index_does_not_crash():
    """tool_calls[].index arriving as a list or object used to raise
    TypeError in dict.setdefault - the delta is diagnosed, not fatal."""
    for idx in ("[0]", '{"i":0}'):
        text = (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":'
            f"{idx},"
            '"function":{"name":"f","arguments":"{}"}}]}}]}\n\n'
            "data: [DONE]\n\n"
        )
        report = diagnose(text)  # must not raise
        assert isinstance(report.findings, list)


def test_tool_call_identified_by_id_when_index_is_null():
    """'index': null with a real 'id' must key the call by its id -
    .get('index', fallback) never reaches the fallback when the key
    exists with a null value."""
    text = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":null,'
        '"id":"call_9","function":{"name":"f","arguments":"{\\"a\\":"}}]}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":null,'
        '"id":"call_9","function":{"arguments":"1}"}}]}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )
    report = diagnose(text)
    assert report.healthy, [f.to_dict() for f in report.findings]


def test_two_anonymous_tool_calls_are_not_merged():
    """Two calls with neither index nor id are still two calls: a
    delta carrying a function name starts a new one. Merging them
    concatenated both arguments strings into invalid JSON and
    produced a false unparseable-tool-arguments error."""
    text = (
        'data: {"choices":[{"delta":{"tool_calls":[{"function":'
        '{"name":"a","arguments":"{}"}}]}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"function":'
        '{"name":"b","arguments":"{}"}}]}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )
    report = diagnose(text)
    assert report.stats["tool_calls_started"] == 2
    assert "unparseable-tool-arguments" not in ids(report)
    assert report.healthy, [f.to_dict() for f in report.findings]


def test_deeply_nested_payload_does_not_crash():
    """json.loads raises RecursionError (not ValueError) once a
    payload is nested tens of thousands of levels deep. Every parse
    site must treat that as a malformed payload, not an exception."""
    deep = "[" * 20000 + "]" * 20000
    report = diagnose(f"data: {deep}\n\ndata: [DONE]\n\n")
    assert "invalid-json-payload" in ids(report)

    chunk = {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"name": "f", "arguments": deep}},
    ]}}]}
    text = (
        f"data: {json.dumps(chunk)}\n\n"
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )
    report = diagnose(text)  # arguments parse site must not raise
    assert "unparseable-tool-arguments" in ids(report)


def test_null_payload_is_flagged_not_healthy():
    """'data: null' parses as JSON (to None) but is not a chunk
    object. It used to slip past the invalid-json check and report
    the stream HEALTHY with zero findings."""
    report = diagnose("data: null\n\ndata: [DONE]\n\n")
    assert "invalid-json-payload" in ids(report)
    assert not report.healthy


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
