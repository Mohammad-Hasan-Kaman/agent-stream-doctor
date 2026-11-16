# live-smoke.ps1 - end-to-end smoke test of `record` + `analyze`
# against a REAL OpenAI-compatible endpoint, from this Windows PC.
#
# Configuration is via environment variables (no credentials in code):
#   ASD_BASE_URL   full URL of the /chat/completions endpoint (required)
#   ASD_MODEL      model name to request (required)
#   ASD_API_KEY    bearer key (optional; or set OPENAI_API_KEY instead)
#   ASD_REPO_DIR   checkout of agent-stream-doctor to run the code from
#                  (default: C:\Users\Nik\agent-stream-doctor)
#   ASD_MESSAGE    prompt to send (default asks for a Persian sentence,
#                  so the response exercises the non-ASCII UTF-8 path)
#
# Example:
#   $env:ASD_BASE_URL = "https://api.openai.com/v1/chat/completions"
#   $env:ASD_MODEL    = "gpt-4o-mini"
#   $env:ASD_API_KEY  = "sk-..."
#   powershell -ExecutionPolicy Bypass -File live-smoke.ps1
#
# Exit-code key (printed at the end): 0 = healthy stream,
# 1 = problems found in the stream (a diagnosis, not a smoke
# failure), 2 = usage/request error (the smoke itself failed).

$ErrorActionPreference = 'Continue'

if (-not $env:ASD_BASE_URL) { Write-Host 'ASD_BASE_URL is not set'; exit 2 }
if (-not $env:ASD_MODEL)    { Write-Host 'ASD_MODEL is not set'; exit 2 }

$repoDir = $env:ASD_REPO_DIR
if (-not $repoDir) { $repoDir = 'C:\Users\Nik\agent-stream-doctor' }
if (-not (Test-Path (Join-Path $repoDir 'src\agent_stream_doctor'))) {
    Write-Host "repo checkout not found at $repoDir (set ASD_REPO_DIR)"
    exit 2
}
$env:PYTHONPATH = Join-Path $repoDir 'src'

$message = $env:ASD_MESSAGE
if (-not $message) { $message = 'Write one short sentence in Persian.' }

$stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$capture = Join-Path $PSScriptRoot "smoke-$stamp.txt"
$report  = Join-Path $PSScriptRoot "smoke-$stamp.report.json"

Write-Host "== record: $env:ASD_BASE_URL (model $env:ASD_MODEL)"
$recordArgs = @(
    '-m', 'agent_stream_doctor.cli', 'record',
    '--base-url', $env:ASD_BASE_URL,
    '--model', $env:ASD_MODEL,
    '--message', $message,
    '--out', $capture,
    '--save-report', $report
)
if ($env:ASD_API_KEY) { $recordArgs += @('--api-key', $env:ASD_API_KEY) }
& python @recordArgs
$recordExit = $LASTEXITCODE
Write-Host "record exit code: $recordExit"

if ($recordExit -eq 2) {
    Write-Host 'record failed (usage/request error) - smoke stopped.'
    exit 2
}

Write-Host ''
Write-Host "== analyze: $capture"
& python -m agent_stream_doctor.cli analyze $capture
$analyzeExit = $LASTEXITCODE
Write-Host "analyze exit code: $analyzeExit"

Write-Host ''
Write-Host "capture file : $capture"
Write-Host "report (JSON): $report"
Write-Host 'Reminder: 0 = healthy, 1 = problems found in the stream, 2 = the request itself failed.'
