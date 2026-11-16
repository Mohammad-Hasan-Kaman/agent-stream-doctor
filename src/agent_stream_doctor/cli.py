"""Capture a live chat-completion stream to a file and diagnose it.

Two subcommands:

* ``record``  : perform the request and save the raw SSE text, then
                analyse it. Requires ``requests`` at runtime -
                imported lazily so the library itself stays
                dependency-free.
* ``analyze`` : offline analysis of an already-captured stream file.

Exit codes: 0 = healthy, 1 = problems found, 2 = usage error
(including unreadable files and failed requests - never a traceback).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .doctor import diagnose
from .models import Severity


def _format_report(report, as_json: bool) -> str:
    if as_json:
        return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    lines: List[str] = []
    lines.append("agent-stream-doctor report")
    lines.append("-" * 40)
    for key, val in report.stats.items():
        if val is not None:
            lines.append(f"  {key}: {val}")
    lines.append("")
    if not report.findings:
        lines.append("No findings. Stream looks healthy.")
    icon = {
        Severity.ERROR: "ERROR  ",
        Severity.WARNING: "WARN   ",
        Severity.INFO: "INFO   ",
    }
    for f in report.findings:
        lines.append(f"[{icon[f.severity]}] {f.check_id}")
        lines.append(f"         {f.message}")
        if f.evidence:
            lines.append(f"         evidence: {f.evidence}")
        if f.explanation:
            lines.append(f"         why: {f.explanation}")
        lines.append("")
    lines.append(report.summary_line())
    return "\n".join(lines)


def cmd_record(args: argparse.Namespace) -> int:
    try:
        import requests
    except ImportError:
        print(
            "The record command needs the 'requests' package: pip install requests",
            file=sys.stderr,
        )
        return 2

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    payload = {"model": args.model, "stream": True}
    if args.message:
        payload["messages"] = [{"role": "user", "content": args.message}]
    elif args.messages_file:
        try:
            with open(args.messages_file, encoding="utf-8") as fh:
                payload["messages"] = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"Could not read --messages-file: {exc}", file=sys.stderr)
            return 2
    else:
        print("Provide --message or --messages-file", file=sys.stderr)
        return 2

    collected = bytearray()
    try:
        with requests.post(args.base_url, headers=headers, json=payload, stream=True,
                           timeout=args.timeout) as resp:
            resp.raise_for_status()
            with open(args.out, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    collected.extend(chunk)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Could not write the capture file: {exc}", file=sys.stderr)
        return 2

    # Capture the raw bytes exactly as they arrived. The previous
    # iter_lines(decode_unicode=True) path decoded with resp.encoding,
    # which falls back to a guessed ISO-8859-1 when the server sends
    # no charset (many OpenAI-compatible routers don't) - mojibaking
    # every non-ASCII stream and writing the corruption to disk as
    # the 'raw' capture. SSE is UTF-8 by definition; bytes that are
    # not valid UTF-8 become U+FFFD here and surface as findings.
    text = bytes(collected).decode("utf-8", errors="replace")
    report = diagnose(text)
    print(_format_report(report, as_json=args.json))
    if args.save_report:
        with open(args.save_report, "w", encoding="utf-8") as fh:
            fh.write(_format_report(report, as_json=True))
    return 0 if report.healthy else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    try:
        # errors="replace": a capture containing a few invalid UTF-8
        # bytes (exactly the kind of proxy mangling this tool exists
        # to diagnose - and exactly what `record` may legitimately
        # save) should be diagnosed, not refused as unreadable.
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (OSError, UnicodeError) as exc:
        print(f"Could not read {args.file}: {exc}", file=sys.stderr)
        return 2
    report = diagnose(text)
    print(_format_report(report, as_json=args.json))
    return 0 if report.healthy else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-stream-doctor",
        description="Diagnose OpenAI-compatible LLM streaming responses.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="call a streaming endpoint, capture and diagnose")
    p_rec.add_argument("--base-url", required=True, help="full URL of /chat/completions")
    p_rec.add_argument("--model", required=True)
    p_rec.add_argument("--message", help="single user message to send")
    p_rec.add_argument("--messages-file", help="JSON file with a full messages array")
    p_rec.add_argument("--api-key", default=None, help="Bearer token (or set OPENAI_API_KEY)")
    p_rec.add_argument("--timeout", type=int, default=300)
    p_rec.add_argument("--out", default="stream.txt", help="where to save the raw SSE text")
    p_rec.add_argument("--save-report", help="also write the JSON report to this path")

    p_ana = sub.add_parser("analyze", help="diagnose an already-captured stream file")
    p_ana.add_argument("file", help="raw SSE text captured from a stream")

    for p in (p_rec, p_ana):
        p.add_argument("--json", action="store_true", help="machine-readable output")

    args = parser.parse_args(argv)
    api_key = getattr(args, "api_key", None)
    if args.command == "record" and not api_key:
        import os
        args.api_key = os.environ.get("OPENAI_API_KEY")

    if args.command == "record":
        return cmd_record(args)
    return cmd_analyze(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
