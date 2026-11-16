# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- The analyzer no longer crashes on valid JSON with an unexpected shape
  (e.g. `delta` as a string, `choices` as a string, `"function": null`);
  such chunks now produce findings instead of an `AttributeError`.
- `data-after-done` now detects chunks arriving after a single `[DONE]`
  sentinel; previously only a second `[DONE]` triggered it, and trailing
  chunks after one `[DONE]` were reported as healthy.
- A completed tool call no longer triggers a false `empty-content-stream`
  error, and a stream containing only `[DONE]` is now reported as an
  empty stream instead of healthy.
- SSE parser: a UTF-8 BOM no longer silently drops the first chunk,
  events carry their real line numbers, a payload split across several
  `data:` lines parses as one event, content sent as a list of parts is
  counted, and payloads that are valid JSON but not objects are flagged.
- CLI: unreadable input files, an unreadable `--messages-file`, and
  failed `record` requests now print a one-line error and exit with
  code 2 instead of a traceback.

## [0.2.0] - 2026-10-21

### Fixed

- `from agent_stream_doctor import diagnose` now works. The package
  `__init__` did not re-export anything, so the import documented in the
  README raised an `ImportError`. `diagnose`, `Report`, `Finding` and
  `Severity` are now exported and listed in `__all__`.

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
