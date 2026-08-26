# Contributing to agent-stream-doctor

Thanks for your interest in improving this project!

## Reporting bugs

Open an [issue](https://github.com/Mohammad-Hasan-Kaman/agent-stream-doctor/issues) and include:

1. The raw stream capture (the `stream.txt` saved by `record`) - **scrub any API keys and private prompt content first**
2. The full report output (`agent-stream-doctor analyze stream.txt --json`)
3. Provider/router/model names if you can share them

A failing stream capture is worth a thousand stack traces. If you cannot share the capture, describe the exact request shape instead.

## Suggesting features

Check detection is the core of this tool. Proposals for new checks should include:

- What wire-level pattern the check detects (with an example SSE snippet)
- Which real providers/routers produce it
- Severity you would expect (error / warning / info)

## Submitting code

1. Fork and create a feature branch from `main`
2. Add tests - every new check needs at least one fixture stream and one test
3. Run `pytest` and make sure all tests pass
4. Keep the core library dependency-free (stdlib only); `requests` may only be imported lazily inside the `record` command
5. Open a pull request with a clear description of what changed and why

## Code style

- Python 3.9+ compatible
- Type hints on public functions
- Every finding must ship with an entry in `EXPLANATIONS` so reports stay educational
