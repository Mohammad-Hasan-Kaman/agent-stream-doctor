"""The core diagnostic checks.

``diagnose()`` consumes the raw SSE text of a chat-completion stream and
runs every check, producing a :class:`~agent_stream_doctor.models.Report`.

All checks are pure functions over the captured text - no network access
is required to analyse a stream you have already saved.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import Finding, Report, Severity
from .sse import (
    chunk_content_delta,
    chunk_finish_reason,
    chunk_reasoning_text,
    chunk_role,
    chunk_tool_call_deltas,
    parse_sse_lines,
)

_DONE = "[DONE]"


def _ev(chunk: Dict[str, Any]) -> str:
    """Compact evidence string for a chunk."""
    import json

    try:
        return json.dumps(chunk)[:200]
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(chunk)[:200]


def diagnose(text: str) -> Report:
    """Analyse one raw OpenAI-compatible SSE stream and return a report."""
    findings: List[Finding] = []
    events, sse_errors = parse_sse_lines(text)

    # ---- transport-level checks -------------------------------------
    if sse_errors:
        first = sse_errors[0]
        findings.append(
            Finding(
                "malformed-sse-line",
                Severity.ERROR,
                f"{len(sse_errors)} line(s) are not valid SSE "
                f"(first at line {first.line_no}: {first.reason!r})",
                evidence=first.raw,
            )
        )

    data_events = [e for e in events if not e.is_done_sentinel]
    done_events = [e for e in events if e.is_done_sentinel]

    bad_json = [e for e in data_events if e.json_error]
    if bad_json:
        first = bad_json[0]
        findings.append(
            Finding(
                "invalid-json-payload",
                Severity.ERROR,
                f"{len(bad_json)} 'data:' payload(s) are not valid JSON "
                f"(first error: {first.json_error})",
                evidence=first.raw_data[:200],
            )
        )

    chunks: List[Dict[str, Any]] = [
        e.json_value for e in data_events if isinstance(e.json_value, dict)
    ]

    # ---- stream-shape checks ----------------------------------------
    stats: Dict[str, Optional[str]] = {
        "data_chunks": len(data_events),
        "done_sentinels": len(done_events),
        "json_errors": len(bad_json),
        "sse_line_errors": len(sse_errors),
    }

    if len(done_events) > 1:
        findings.append(
            Finding(
                "data-after-done",
                Severity.WARNING,
                f"Stream contains {len(done_events)} '[DONE]' sentinels; "
                "everything after the first is unreachable for most clients.",
            )
        )

    # Content / reasoning / finish-reason aggregation.
    roles = set()
    content_parts: List[str] = []
    reasoning_parts: List[str] = []
    finish_reasons: List[Optional[str]] = []
    tool_calls: Dict[Any, Dict[str, Any]] = {}

    for ch in chunks:
        role = chunk_role(ch)
        if role:
            roles.add(role)

        c = chunk_content_delta(ch)
        if isinstance(c, str):
            content_parts.append(c)

        reasoning_parts.append(chunk_reasoning_text(ch))

        fr = chunk_finish_reason(ch)
        if fr is not None:
            finish_reasons.append(fr)

        for tc in chunk_tool_call_deltas(ch):
            idx = tc.get("index", tc.get("id"))
            entry = tool_calls.setdefault(idx, {"id": None, "name": "", "arguments": ""})
            if tc.get("id"):
                entry["id"] = tc["id"]
            if tc.get("function", {}).get("name"):
                entry["name"] = tc["function"]["name"]
            args = tc.get("function", {}).get("arguments")
            if isinstance(args, str):
                entry["arguments"] += args

    content = "".join(content_parts)
    reasoning = "".join(reasoning_parts)

    stats.update(
        {
            "content_chars": len(content),
            "reasoning_chars": len(reasoning),
            "finish_reasons": finish_reasons or None,
            "roles_seen": sorted(roles) or None,
            "tool_calls_started": len(tool_calls) or None,
        }
    )

    # ---- empty stream -------------------------------------------------
    if not chunks and not done_events and not sse_errors:
        findings.append(
            Finding(
                "empty-stream",
                Severity.ERROR,
                "Stream contained no completion data at all - zero data "
                "chunks, no '[DONE]'. The server closed an empty response.",
            )
        )
        stats["content_chars"] = 0
        stats["reasoning_chars"] = 0
        report = Report(findings=findings, stats=stats)
        return report

    # ---- reasoning-only responses --------------------------------------
    if chunks and not content.strip():
        if reasoning.strip():
            findings.append(
                Finding(
                    "reasoning-only-response",
                    Severity.ERROR,
                    f"Model streamed {len(reasoning)} chars of reasoning but "
                    "never emitted any final answer content.",
                )
            )
        else:
            findings.append(
                Finding(
                    "empty-content-stream",
                    Severity.ERROR,
                    "Stream ended normally but every content delta was empty - "
                    "the model produced nothing observable.",
                )
            )

    # ---- finish reason --------------------------------------------------
    non_null = [f for f in finish_reasons if f]
    if not non_null:
        if chunks:
            findings.append(
                Finding(
                    "missing-finish-reason",
                    Severity.ERROR,
                    "No chunk carried a finish_reason; the choice never "
                    "terminated properly.",
                )
            )
    elif len(set(non_null)) > 1:
        findings.append(
            Finding(
                "inconsistent-finish-reason",
                Severity.WARNING,
                f"Multiple distinct finish_reason values in one stream: "
                f"{sorted(set(non_null))}. A router may be merging streams.",
            )
        )
    # ---- [DONE] sentinel -------------------------------------------------
    if chunks and not done_events:
        findings.append(
            Finding(
                "stream-ended-without-done",
                Severity.WARNING,
                "Stream ended without a '[DONE]' sentinel. Clients that wait "
                "for it will hang; others treat the close as implicit end.",
            )
        )

    # ---- tool calls -------------------------------------------------------
    if tool_calls:
        finished_tool_calls = any(f == "tool_calls" for f in non_null)
        if not finished_tool_calls:
            findings.append(
                Finding(
                    "incomplete-tool-call",
                    Severity.ERROR,
                    "Tool-call deltas arrived but finish_reason was never "
                    "'tool_calls' - your agent loop never received a complete "
                    "call.",
                )
            )
        for idx, entry in tool_calls.items():
            import json as _json

            try:
                _json.loads(entry["arguments"] or "{}")
            except ValueError as exc:
                findings.append(
                    Finding(
                        "unparseable-tool-arguments",
                        Severity.ERROR,
                        f"Tool call #{idx} ({entry['name'] or 'unknown'}) has "
                        f"arguments that are not valid JSON: {exc}",
                        evidence=entry["arguments"][:200],
                    )
                )

    # ---- misc info ---------------------------------------------------------
    if not roles and chunks:
        findings.append(
            Finding(
                "role-not-announced",
                Severity.INFO,
                "No chunk announced delta.role. Harmless for most clients, "
                "but strict consumers may rely on it.",
            )
        )

    return Report(findings=findings, stats=stats)
