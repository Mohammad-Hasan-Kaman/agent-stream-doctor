"""Tests for the SSE parser itself: framing, line numbers, tolerance."""
from agent_stream_doctor.sse import parse_sse_lines


def test_events_carry_real_line_numbers():
    events, errors = parse_sse_lines(
        'data: {"a":1}\n\ndata: {broken\n\ndata: [DONE]\n\n'
    )
    assert [e.line_no for e in events] == [1, 3, 5]
    assert errors == []


def test_frameless_stream_splits_per_payload():
    # Captures handed over by HTTP clients often have no blank-line
    # separators at all: one data: line after another.
    events, _ = parse_sse_lines('data: {"a":1}\ndata: {"b":2}\ndata: [DONE]\n')
    assert [e.raw_data for e in events] == ['{"a":1}', '{"b":2}', "[DONE]"]
    assert events[-1].is_done_sentinel


def test_multiline_data_payload_is_one_event():
    # Legal SSE: one JSON object split across two data: lines.
    events, _ = parse_sse_lines(
        'data: {"choices":[{"delta":{"content":\ndata: "Hi"}}]}\n\ndata: [DONE]\n\n'
    )
    assert len(events) == 2
    assert events[0].json_error is None
    assert events[0].json_value["choices"][0]["delta"]["content"] == "Hi"


def test_broken_payload_stays_one_event_per_frame():
    events, _ = parse_sse_lines("data: {broken\n\ndata: [DONE]\n\n")
    assert len(events) == 2
    assert events[0].json_error is not None


def test_bom_does_not_eat_the_first_chunk():
    events, _ = parse_sse_lines('\ufeffdata: {"a":1}\n\ndata: [DONE]\n\n')
    assert len(events) == 2
    assert events[0].json_value == {"a": 1}
    assert events[0].line_no == 1


def test_comments_and_unknown_fields_are_legal():
    events, errors = parse_sse_lines(
        ": keep-alive\nevent: message\nid: 7\ndata: {\"a\":1}\n\n"
    )
    assert len(events) == 1
    assert errors == []


def test_colonless_line_is_a_parse_error_with_line_number():
    _, errors = parse_sse_lines('data: {"a":1}\n\nnonsense line\n\n')
    assert len(errors) == 1
    assert errors[0].line_no == 3
