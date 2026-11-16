# Live `record` smoke test (run on the Windows PC)

The analyzer half of agent-stream-doctor is fully covered by offline
tests, but `record` only proves itself against a real endpoint, from
a real network: on the PC, set three environment variables —
`ASD_BASE_URL` to the full `/chat/completions` URL of any
OpenAI-compatible endpoint you have access to, `ASD_MODEL` to a model
it serves, and `ASD_API_KEY` to your key for it (or set
`OPENAI_API_KEY` instead) — then run
`powershell -ExecutionPolicy Bypass -File live-smoke.ps1` from this
folder. The script records one short stream (the default prompt asks
for a Persian sentence, so the reply exercises the non-ASCII UTF-8
path that the 2026-11-16 audit found broken), saves the raw capture
and a JSON report next to the script, then re-analyzes the capture
offline and prints both exit codes: `record` and `analyze` should
agree — 0 for a healthy stream, 1 when the stream itself has
problems (that is a successful diagnosis, not a smoke failure), and
2 only when the request itself failed, which is the one outcome that
means the smoke did not run. Point `ASD_REPO_DIR` at a different
checkout if the code should come from somewhere other than
`C:\Users\Nik\agent-stream-doctor`.
