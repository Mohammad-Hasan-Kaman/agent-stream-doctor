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

    bad_json = [
        e
        for e in data_events
        if e.json_error or (e.json_value is not None and not isinstance(e.json_value, dict))
    ]
    if bad_json:
        first = bad_json[0]
        detail = (
            f"first error: {first.json_error}"
            if first.json_error
            else "first payload is valid JSON but not an object"
        )
        findings.append(
            Finding(
                "invalid-json-payload",
                Severity.ERROR,
                f"{len(bad_json)} 'data:' payload(s) are not valid JSON "
                f"objects ({detail})",
                evidence=first.raw_data[:200],
            )
        )

    chunks: List[Dict[str, Any]] = [
        e.json_value for e in data_events if isinstance(e.json_value, dict)
    ]

    # ---- stream-shape checks ----------------------------------------
    stats: Dict[str, Any] = {
        "data_chunks": len(data_events),
        "done_sentinels": len(done_events),
        "json_errors": len(bad_json),
        "sse_line_errors": len(sse_errors),
    }

    events_after_done = 0
    seen_done = False
    for e in events:
        if seen_done:
            events_after_done += 1
        if e.is_done_sentinel:
            seen_done = True
    if events_after_done:
        findings.append(
            Finding(
                "data-after-done",
                Severity.WARNING,
                f"{events_after_done} event(s) arrived after the first "
                "'[DONE]' sentinel. Clients typically stop reading at "
                "'[DONE]', so anything after it is silently lost.",
            )
        )

    # Content / reasoning / finish-reason aggregation.
    roles = set()
    content_parts: List[str] = []
    reasoning_parts: List[str] = []
    finish_reasons: List[Optional[str]] = []
    tool_calls: Dict[Any, Dict[str, Any]] = {}
    anon_seq = 0
    last_anon_key: Optional[Any] = None

    for ch in chunks:
        role = chunk_role(ch)
        if role:
            roles.add(role)

        c = chunk_content_delta(ch)
        if isinstance(c, str):
            content_parts.append(c)

        reasoning_parts.append(chunk_reasoning_text(ch))

        fr = chunk_finish_reason(ch)
        if isinstance(fr, str):
            # A finish_reason that is not a string (a router emitting
            # 123, true, {...}) is not a termination. Counting it
            # would both lie about the stream having finished and
            # crash the set()/sorted() aggregation below on
            # unhashable or mutually incomparable values.
            finish_reasons.append(fr)

        for tc in chunk_tool_call_deltas(ch):
            idx = tc.get("index")
            if idx is None:
                # 'index' may be present but null while the call is
                # identified by 'id' alone.
                idx = tc.get("id")
            if idx is not None and not isinstance(idx, (str, int, float, bool)):
                # A list/object index cannot key a call - and would
                # crash setdefault() as an unhashable key. Treat the
                # delta as anonymous instead.
                idx = None
            if idx is None:
                # No usable index or id. Deltas that start a call
                # (they carry an id or a function name) open a fresh
                # anonymous entry; bare continuation fragments extend
                # the previous one. Without this, two distinct calls
                # merged into one entry and their arguments strings
                # concatenated into invalid JSON.
                fn_probe = tc.get("function")
                starts_new = bool(tc.get("id")) or (
                    isinstance(fn_probe, dict) and bool(fn_probe.get("name"))
                )
                if last_anon_key is None or starts_new:
                    anon_seq += 1
                    last_anon_key = ("__anonymous__", anon_seq)
                    tool_calls[last_anon_key] = {
                        "id": None,
                        "name": "",
                        "arguments": "",
                    }
                idx = last_anon_key
            entry = tool_calls.setdefault(idx, {"id": None, "name": "", "arguments": ""})
            if tc.get("id"):
                entry["id"] = tc["id"]
            fn = tc.get("function")
            if isinstance(fn, dict):
                if fn.get("name"):
                    entry["name"] = fn["name"]
                args = fn.get("arguments")
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
    if not chunks and not data_events and not sse_errors:
        findings.append(
            Finding(
                "empty-stream",
                Severity.ERROR,
                "Stream contained no completion data at all - zero data "
                "chunks. The server closed an empty response.",
            )
        )
        stats["content_chars"] = 0
        stats["reasoning_chars"] = 0
        report = Report(findings=findings, stats=stats)
        return report

    # ---- reasoning-only responses --------------------------------------
    if chunks and not content.strip() and not tool_calls:
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
                label = idx[1] if isinstance(idx, tuple) else idx
                findings.append(
                    Finding(
                        "unparseable-tool-arguments",
                        Severity.ERROR,
                        f"Tool call #{label} ({entry['name'] or 'unknown'}) has "
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
