"""Data model for diagnostic findings and reports."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


#: Short, practical explanations shown under each finding so the output
#: teaches instead of just alarming.
EXPLANATIONS: Dict[str, str] = {
    "empty-stream": (
        "The server closed the stream without sending any completion chunks. "
        "Check that the endpoint actually supports 'stream': true, verify the "
        "model name, and look for upstream gateway errors."
    ),
    "reasoning-only-response": (
        "The model streamed reasoning/thinking content but never produced a "
        "final answer. Some routers drop or mis-map reasoning channels; your "
        "client may need to fall back to a non-streaming request or a "
        "different model when this pattern appears."
    ),
    "missing-finish-reason": (
        "No chunk ever carried a finish_reason value. Well-behaved OpenAI-"
        "compatible backends always terminate the choice with 'stop', "
        "'length' or 'tool_calls'. Missing finish_reason usually means the "
        "connection was cut or the proxy rewrote the stream."
    ),
    "inconsistent-finish-reason": (
        "More than one distinct finish_reason appeared in a single choice "
        "stream. This usually means the router merged or replayed streams."
    ),
    "empty-content-stream": (
        "Chunks arrived and the stream ended normally, but every content "
        "delta was an empty string. The model spent the whole response on "
        "nothing observable - often a provider-side filter or a broken "
        "template."
    ),
    "malformed-sse-line": (
        "A line in the stream does not follow the Server-Sent Events format "
        "(field: value). A proxy in front of the API is probably mangling "
        "the stream."
    ),
    "invalid-json-payload": (
        "A 'data:' payload could not be parsed as JSON. Truncated writes or "
        "double-encoded responses from a proxy cause this."
    ),
    "data-after-done": (
        "Chunks were sent after the '[DONE]' sentinel. Clients typically "
        "stop reading at '[DONE]', so these chunks are silently lost - a "
        "clear protocol violation on the server side."
    ),
    "stream-ended-without-done": (
        "The stream ended without the '[DONE]' sentinel. Some clients wait "
        "for it forever and hang. Others treat the close as implicit end; "
        "either way it violates the OpenAI wire contract."
    ),
    "incomplete-tool-call": (
        "Tool-call deltas arrived but the stream never finished with "
        "finish_reason='tool_calls'. The calling model intended to invoke a "
        "tool and your agent loop never received a complete call."
    ),
    "unparseable-tool-arguments": (
        "The concatenated 'arguments' fragments of a tool call do not form "
        "valid JSON. Streaming truncation cut the arguments mid-object."
    ),
    "role-not-announced": (
        "No chunk announced delta.role. Harmless for most clients, but a "
        "few strict consumers rely on the first chunk to identify the "
        "assistant turn."
    ),
}


@dataclass
class Finding:
    """One concrete problem (or note) detected in a stream."""

    check_id: str
    severity: Severity
    message: str
    evidence: Optional[str] = None

    @property
    def explanation(self) -> str:
        return EXPLANATIONS.get(self.check_id, "")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "check_id": self.check_id,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.evidence:
            out["evidence"] = self.evidence
        return out


@dataclass
class Report:
    """Aggregated result of analysing one stream."""

    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def infos(self) -> List[Finding]:
        return [f for f in self.findings if f.severity is Severity.INFO]

    @property
    def healthy(self) -> bool:
        """A stream is healthy when nothing rose above INFO severity."""
        return not self.errors and not self.warnings

    def summary_line(self) -> str:
        state = "HEALTHY" if self.healthy else (
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )
        return f"Result: {state}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
        }
