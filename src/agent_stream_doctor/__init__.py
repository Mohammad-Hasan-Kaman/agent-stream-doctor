"""agent-stream-doctor: diagnose broken LLM streaming responses.

Zero-dependency diagnostics for OpenAI-compatible chat completion streams:
detect empty streams, reasoning-only replies, missing finish_reason,
malformed SSE, and incomplete tool calls.
"""

from .doctor import diagnose
from .models import Finding, Report, Severity

__version__ = "0.2.1"

__all__ = ["diagnose", "Report", "Finding", "Severity", "__version__"]
