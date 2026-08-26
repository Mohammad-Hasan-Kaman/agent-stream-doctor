# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-08-26

### Added

- Core `diagnose()` analyzer for raw OpenAI-compatible SSE streams
- 12 checks: empty-stream, reasoning-only-response, empty-content-stream,
  missing-finish-reason, inconsistent-finish-reason, malformed-sse-line,
  invalid-json-payload, data-after-done, stream-ended-without-done,
  incomplete-tool-call, unparseable-tool-arguments, role-not-announced
- Reasoning recognition across `reasoning_content` / `reasoning` / `thinking` delta shapes
- CLI with `record` (live capture + diagnosis) and `analyze` (offline file)
  subcommands, JSON output mode, script-friendly exit codes
- Full test suite covering every failure class
- GitHub Actions CI (Python 3.9-3.13)
