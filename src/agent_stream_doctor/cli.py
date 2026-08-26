"""Capture a live chat-completion stream to a file and diagnose it.

Two modes:

* ``--record``  : perform the request and save the raw SSE text, then
                  analyse it. Requires only ``requests`` (or httpx) at
                  runtime - imported lazily so the library itself stays
                  dependency-free.
* ``--analyze`` : offline analysis of an already-captured stream file.
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
        import requests  # noqa: F401
    except ImportError:
        print(
            "The --record mode needs the 'requests' package: pip install requests",
            file=sys.stderr,
        )
        return 2

    import requests

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    payload = {"model": args.model, "stream": True}
    if args.message:
        payload["messages"] = [{"role": "user", "content": args.message}]
    elif args.messages_file:
        with open(args.messages_file, encoding="utf-8") as fh:
            payload["messages"] = json.load(fh)
    else:
        print("Provide --message or --messages-file", file=sys.stderr)
        return 2

    collected = []
    with requests.post(args.base_url, headers=headers, json=payload, stream=True,
                       timeout=args.timeout) as resp:
        resp.raise_for_status()
        with open(args.out, "w", encoding="utf-8") as fh:
            for raw in resp.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                fh.write(raw + "\n")
                collected.append(raw)

    text = "\n".join(collected)
    report = diagnose(text)
    print(_format_report(report, as_json=args.json))
    if args.save_report:
        with open(args.save_report, "w", encoding="utf-8") as fh:
            fh.write(_format_report(report, as_json=True))
    return 0 if report.healthy else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    with open(args.file, encoding="utf-8") as fh:
        text = fh.read()
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
