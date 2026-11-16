# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.2] - 2026-11-16

### Fixed

- `diagnose()` no longer crashes on a non-string `finish_reason`
  (object, list, number, NaN); only string values count as stream
  termination, anything else surfaces as `missing-finish-reason`.
- Tool-call deltas with an unhashable `index` no longer crash, and
  distinct tool calls are no longer merged into one another:
  `index: null` no longer shadows a usable `id`, and a delta carrying
  a name or id opens a fresh call instead of concatenating arguments
  into a false `unparseable-tool-arguments`.
- Deeply nested JSON payloads (~20k levels) now produce findings
  instead of a `RecursionError` crash, in event payloads, the
  completeness probe, and tool-argument reassembly.
- A stream of `data: null` payloads is now flagged as
  `invalid-json-payload` instead of being reported healthy.
- SSE lines are split strictly on CR/LF. Unicode line separators
  (U+2028, U+2029, U+0085) inside JSON strings no longer shred a
  valid stream into phantom malformed-line and invalid-JSON errors,
  and the field value trim now removes exactly one leading space,
  as the SSE spec requires.
- `record` saves the raw response bytes verbatim and decodes a copy
  as UTF-8. Previously it decoded with the server's guessed charset
  (ISO-8859-1 when none was sent, the normal case for
  `text/event-stream`), which mojibaked every non-ASCII stream and
  wrote the corruption to disk as the capture. `analyze` now reads
  captures with replacement characters instead of refusing files
  that contain invalid UTF-8 bytes.
- CLI: `--save-report` to an unwritable path, `--timeout 0` or a
  negative timeout, and a broken pipe on stdout now all end with a
  clean one-line error and a documented exit code (2, 2, and 1)
  instead of tracebacks or an exit-120 flush dump.

### Tests

34 -> 49 tests, all passing, including a stubbed-`requests` record
test that captures a one-byte-at-a-time UTF-8 stream byte-for-byte.

## [0.2.1] - 2026-11-16

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
