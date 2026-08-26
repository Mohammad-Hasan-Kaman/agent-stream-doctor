"""Minimal Server-Sent Events parser for OpenAI-compatible chat streams.

Deliberately dependency-free and tolerant: the goal is to *diagnose*
malformed input, not to reject it early. Every deviation is recorded as
a finding instead of raising.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class SSEParseError:
    """A line that could not be parsed as valid SSE."""

    def __init__(self, line_no: int, raw: str, reason: str) -> None:
        self.line_no = line_no
        self.raw = raw
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SSEParseError(line {self.line_no}: {self.reason})"


class ParsedEvent:
    """One 'data:' payload extracted from an SSE byte stream."""

    def __init__(self, line_no: int, raw_data: str) -> None:
        self.line_no = line_no
        self.raw_data = raw_data
        self.json_value: Optional[Any] = None
        self.json_error: Optional[str] = None
        if raw_data.strip() == "[DONE]":
            self.is_done_sentinel = True
        else:
            self.is_done_sentinel = False
            import json

            try:
                self.json_value = json.loads(raw_data)
            except ValueError as exc:
                self.json_error = str(exc)


def parse_sse_lines(text: str):
    """Split an SSE text stream into events and collect malformed lines.

    Returns ``(events, errors)`` where *events* is a list of
    :class:`ParsedEvent` (data payloads only - OpenAI chat streams carry
    everything in ``data``) and *errors* is a list of
    :class:`SSEParseError`.
    """
    events: List[ParsedEvent] = []
    errors: List[SSEParseError] = []
    data_buffer: List[str] = []

    def flush() -> None:
        if data_buffer:
            events.append(ParsedEvent(len(events) + len(errors), "".join(data_buffer)))
            data_buffer.clear()

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\r")
        if line == "":
            # Blank line terminates a multi-line data block.
            flush()
            continue
        if line.startswith(":"):
            # SSE comment / keep-alive.
            continue
        if ":" in line:
            field, _, value = line.partition(":")
            value = value.lstrip(" ")
            if field == "data":
                data_buffer.append(value)
                flush()  # OpenAI sends one JSON object per data line.
            # event:, id:, retry: are legal but unused by OpenAI-style APIs.
            continue
        errors.append(
            SSEParseError(line_no, raw_line[:120], "line has no 'field:' structure")
        )
    flush()
    return events, errors


def chunk_role(chunk: Dict[str, Any]) -> Optional[str]:
    choices = chunk.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    return delta.get("role")


def chunk_content_delta(chunk: Dict[str, Any]) -> Optional[str]:
    choices = chunk.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    return delta.get("content")


def chunk_finish_reason(chunk: Dict[str, Any]) -> Optional[str]:
    choices = chunk.get("choices") or []
    if not choices:
        return None
    return choices[0].get("finish_reason")


def chunk_reasoning_text(chunk: Dict[str, Any]) -> str:
    """Extract reasoning/thinking content from any known vendor shape.

    Covers the common variants seen across OpenAI-compatible routers:

    * ``choices[0].delta.reasoning_content``  (DeepSeek style)
    * ``choices[0].delta.reasoning``          (several aggregators)
    * ``choices[0].delta.thinking``           (some proxies)
    """
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    parts = []
    for key in ("reasoning_content", "reasoning", "thinking"):
        val = delta.get(key)
        if isinstance(val, str):
            parts.append(val)
    return "".join(parts)


def chunk_tool_call_deltas(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
    choices = chunk.get("choices") or []
    if not choices:
        return []
    delta = choices[0].get("delta") or {}
    tc = delta.get("tool_calls")
    return [t for t in tc if isinstance(t, dict)] if isinstance(tc, list) else []


def chunk_has_usage(chunk: Dict[str, Any]) -> bool:
    return isinstance(chunk.get("usage"), dict)
