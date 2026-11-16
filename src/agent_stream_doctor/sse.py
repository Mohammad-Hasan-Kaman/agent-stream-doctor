"""Minimal Server-Sent Events parser for OpenAI-compatible chat streams.

Deliberately dependency-free and tolerant: the goal is to *diagnose*
malformed input, not to reject it early. Every deviation is recorded as
a finding instead of raising.
"""
from __future__ import annotations

import json
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
            try:
                self.json_value = json.loads(raw_data)
            except ValueError as exc:
                self.json_error = str(exc)


def _is_complete_payload(text: str) -> bool:
    """True when *text* is a whole payload: the [DONE] sentinel or JSON
    that parses on its own. Used to decide whether a buffered ``data:``
    block is finished or continues on the next ``data:`` line."""
    if text.strip() == "[DONE]":
        return True
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def parse_sse_lines(text: str):
    """Split an SSE text stream into events and collect malformed lines.

    Returns ``(events, errors)`` where *events* is a list of
    :class:`ParsedEvent` (data payloads only - OpenAI chat streams carry
    everything in ``data``) and *errors* is a list of
    :class:`SSEParseError`.

    Framing rules, in order:

    * a blank line ends the current data block (standard SSE);
    * a ``data:`` block whose joined lines already form a complete
      payload also ends there, so frameless captures (one ``data:``
      line after another, no blank separators - which is what many
      HTTP clients hand you) still split into one event per payload;
    * a payload split across several ``data:`` lines (legal SSE)
      stays buffered until it completes or a blank line ends it.
    """
    if text.startswith("\ufeff"):
        # A UTF-8 BOM saved by some editors/tools would otherwise glue
        # itself to the first field name and silently eat chunk one.
        text = text[1:]

    events: List[ParsedEvent] = []
    errors: List[SSEParseError] = []
    data_buffer: List[str] = []
    buffer_start = 0

    def flush() -> None:
        if data_buffer:
            events.append(ParsedEvent(buffer_start, "\n".join(data_buffer)))
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
                if data_buffer and _is_complete_payload("\n".join(data_buffer)):
                    flush()
                if not data_buffer:
                    buffer_start = line_no
                data_buffer.append(value)
            # event:, id:, retry: are legal but unused by OpenAI-style APIs.
            continue
        errors.append(
            SSEParseError(line_no, raw_line[:120], "line has no 'field:' structure")
        )
    flush()
    return events, errors


def _first_choice(chunk: Any) -> Dict[str, Any]:
    """The first choice object of a chunk, or {} for any other shape.

    Captured streams can contain valid JSON with the *wrong* shape
    (a proxy emitting ``"delta": "text"``, a ``choices`` string, ...).
    A diagnostic tool must report those, never crash on them.
    """
    if not isinstance(chunk, dict):
        return {}
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first = choices[0]
    return first if isinstance(first, dict) else {}


def _delta(chunk: Any) -> Dict[str, Any]:
    delta = _first_choice(chunk).get("delta")
    return delta if isinstance(delta, dict) else {}


def chunk_role(chunk: Dict[str, Any]) -> Optional[str]:
    role = _delta(chunk).get("role")
    return role if isinstance(role, str) else None


def chunk_content_delta(chunk: Dict[str, Any]) -> Optional[str]:
    content = _delta(chunk).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Some routers emit content as a list of parts
        # ([{"type": "text", "text": ...}, ...]) instead of a plain
        # string. The text is real content - count it, or the stream
        # is misreported as empty.
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return None


def chunk_finish_reason(chunk: Dict[str, Any]) -> Optional[str]:
    return _first_choice(chunk).get("finish_reason")


def chunk_reasoning_text(chunk: Dict[str, Any]) -> str:
    """Extract reasoning/thinking content from any known vendor shape.

    Covers the common variants seen across OpenAI-compatible routers:

    * ``choices[0].delta.reasoning_content``  (DeepSeek style)
    * ``choices[0].delta.reasoning``          (several aggregators)
    * ``choices[0].delta.thinking``           (some proxies)
    """
    delta = _delta(chunk)
    parts = []
    for key in ("reasoning_content", "reasoning", "thinking"):
        val = delta.get(key)
        if isinstance(val, str):
            parts.append(val)
    return "".join(parts)


def chunk_tool_call_deltas(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
    tc = _delta(chunk).get("tool_calls")
    return [t for t in tc if isinstance(t, dict)] if isinstance(tc, list) else []


def chunk_has_usage(chunk: Dict[str, Any]) -> bool:
    return isinstance(chunk, dict) and isinstance(chunk.get("usage"), dict)
