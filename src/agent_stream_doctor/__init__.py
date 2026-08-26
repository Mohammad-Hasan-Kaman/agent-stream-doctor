"""agent-stream-doctor: diagnose broken LLM streaming responses.

Zero-dependency diagnostics for OpenAI-compatible chat completion streams:
detect empty streams, reasoning-only replies, missing finish_reason,
malformed SSE, and incomplete tool calls.
"""

__version__ = "0.1.0"
