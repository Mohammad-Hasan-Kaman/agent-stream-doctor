"""Fixtures: realistic raw SSE streams, one per failure class.

The ``hermes_reasoning_only`` stream reproduces the shape reported in
NousResearch/hermes-agent#92803: a long reasoning phase followed by an
empty final answer.
"""
import textwrap


def _chunks(*payloads: str) -> str:
    return "\n\n".join(f"data: {p}" for p in payloads) + "\n\n"


HEALTHY = (
    'data: {"choices":[{"delta":{"role":"assistant","content":"Hel"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"lo world"}}]}\n\n'
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    "data: [DONE]\n\n"
)

EMPTY_STREAM = ""

REASONING_ONLY = _chunks(
    '{"choices":[{"delta":{"role":"assistant","reasoning_content":"Let me think about this problem step by step."}}]}',
    '{"choices":[{"delta":{"reasoning_content":"The answer requires careful analysis of the question."}}]}',
    '{"choices":[{"delta":{"reasoning_content":"Considering all angles... almost there."}}]}',
) + "data: [DONE]\n\n"

MISSING_FINISH_REASON = (
    'data: {"choices":[{"delta":{"role":"assistant","content":"Partial ans"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"wer cut off"}}]}\n\n'
)

MALFORMED_SSE = (
    'data: {"choices":[{"delta":{"role":"assistant","content":"Hi"}}]}\n\n'
    "this line is not valid server-sent-events at all\n\n"
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    "data: [DONE]\n\n"
)

INVALID_JSON = (
    'data: {"choices":[{"delta":{"role":"assistant","content":"Hi"}}]}\n\n'
    "data: {broken json here\n\n"
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    "data: [DONE]\n\n"
)

DATA_AFTER_DONE = HEALTHY + (
    'data: {"choices":[{"delta":{"content":"ghost chunk"}}]}\n\n'
    "data: [DONE]\n\n"
)

NO_DONE_SENTINEL = MISSING_FINISH_REASON  # ends abruptly

TOOL_CALL_TRUNCATED = _chunks(
    '{"choices":[{"delta":{"role":"assistant","tool_calls":[{"index":0,"id":"call_1","function":{"name":"get_weather","arguments":""}}]}}]}',
    '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"city\\": \\"Te"}}]}}]}',
    '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"hran\\""}}]}}]}',
)

TOOL_CALL_COMPLETE = _chunks(
    '{"choices":[{"delta":{"role":"assistant","tool_calls":[{"index":0,"id":"call_1","function":{"name":"get_weather","arguments":"{\\"city\\": \\"Ber"}}]}}]}',
    '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"lin\\"}"}}]}}]}',
    '{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
) + "data: [DONE]\n\n"

EMPTY_CONTENT = _chunks(
    '{"choices":[{"delta":{"role":"assistant","content":""}}]}',
    '{"choices":[{"delta":{"content":""}}]}',
    '{"choices":[{"delta":{},"finish_reason":"stop"}]}',
) + "data: [DONE]\n\n"

USAGE_IN_CHUNKS = (
    'data: {"choices":[{"delta":{"role":"assistant","content":"Hi"}}],'
    '"usage":{"prompt_tokens":1,"completion_tokens":1}}\n\n'
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    "data: [DONE]\n\n"
)
