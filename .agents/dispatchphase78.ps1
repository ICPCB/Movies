# Phase 7-8 Codex Dispatch Orchestration Script
# Run from repo root: .\agents\dispatch-phase7-8.ps1
#
# This script dispatches tickets one at a time via Codex CLI.
# It pauses at human gates for manual review.
#
# Prerequisites:
# - Phase 6 combined run must exist
# - Codex CLI installed and configured
# - venv activated or available at .\venv\

$ErrorActionPreference = "Stop"

$TICKETS = @(
    @{ id = "7-A"; file = "7Amoodaxestestsmetrics.md";       gate = $false },
    @{ id = "7-B"; file = "7Bmoodtriagereport.md";           gate = $true; gate_msg = "Review triage report at docs/superpowers/reports/phase7-mood-triage.md" },
    @{ id = "pre-7-C"; file = "pre7Cfixmergelabelsqueries.md"; gate = $true; gate_msg = "Choose merge_labels fix option (A/B/C)" },
    @{ id = "7-C"; file = "7Clabelfixesgoldmetrics.md";      gate = $true; gate_msg = "Review label provenance for q55 + mood queries" },
    @{ id = "7-D"; file = "7Danalysisphase8proposal.md";     gate = $true; gate_msg = "Approve Phase 8 scope before implementation" },
    @{ id = "8-A"; file = "8Amoodpreprocessor.md";           gate = $false },
    @{ id = "8-B"; file = "8Bsynonymgroups.md";              gate = $false },
    @{ id = "8-C"; file = "8Cpromptrewriting.md";            gate = $false },
    @{ id = "8-D"; file = "8Dsafetyfilter.md";               gate = $false },
    @{ id = "8-E"; file = "8Epipelineintegration.md";        gate = $false },
    @{ id = "8-F"; file = "8Fstresstestqueries.md";          gate = $false },
    @{ id = "8-G"; file = "8Gevalregressioncheck.md";        gate = $true; gate_msg = "Review regression results before accepting Phase 8" }
)

$INBOX = ".agents\inbox\codex"
$OUTBOX = ".agents\outbox\codex"
$LOCK = ".agents\locks\active_ticket.lock"
$REPO = (Get-Location).Path
$SAFE_REPO = $REPO.Replace("\", "/")

function Test-ActiveLock {
    if (-not (Test-Path $LOCK)) {
        return $false
    }

    $lockContent = Get-Content $LOCK -Raw
    $status = $null

    try {
        $parsed = $lockContent | ConvertFrom-Json
        $status = $parsed.status
    } catch {
        if ($lockContent -match "(?m)^\s*status:\s*(\S+)") {
            $status = $Matches[1]
        }
    }

    if ($status -eq "CLOSED") {
        Write-Host "Clearing closed lock:" -ForegroundColor Yellow
        Write-Host $lockContent
        Remove-Item $LOCK -Force
        return $false
    }

    Write-Host "BLOCKED: Active lock exists:" -ForegroundColor Red
    Write-Host $lockContent
    return $true
}

function Dispatch-Ticket {
    param([hashtable]$ticket)

    $id = $ticket.id
    $file = $ticket.file
    $source = Join-Path $INBOX $file

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  Dispatching ticket: $id" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan

    # Check lock
    if (Test-ActiveLock) {
        return $false
    }

    if (-not (Test-Path $source)) {
        Write-Host "BLOCKED: Ticket file not found: $source" -ForegroundColor Red
        return $false
    }

    # Create lock
    @"
ticket_id: $id
agent: codex
start: $(Get-Date -Format o)
status: RUNNING
"@ | Set-Content $LOCK

    # Copy to current.md
    Copy-Item $source (Join-Path $INBOX "current.md") -Force

    # Dispatch
    try {
        Get-Content (Join-Path $INBOX "current.md") -Raw |
            codex exec `
                --cd . `
                --sandbox workspace-write `
                --output-last-message (Join-Path $OUTBOX "current_result.md") `
                -
        if ($LASTEXITCODE -ne 0) {
            throw "codex exec exited with code $LASTEXITCODE"
        }
    } catch {
        Write-Host "Codex dispatch failed: $_" -ForegroundColor Red
        "status: STOPPED`nerror: $_" | Add-Content $LOCK
        return $false
    }

    # Read result
    $result = Join-Path $OUTBOX "current_result.md"
    if (Test-Path $result) {
        Write-Host "`n--- Codex Result ---" -ForegroundColor Yellow
        Get-Content $result
        Write-Host "--- End Result ---`n" -ForegroundColor Yellow
    }

    # Show git status
    Write-Host "`n--- Git Status ---" -ForegroundColor Yellow
    git -c safe.directory="$SAFE_REPO" status --short
    git -c safe.directory="$SAFE_REPO" diff --name-only
    Write-Host "--- End Status ---`n" -ForegroundColor Yellow

    # Close lock
    Remove-Item $LOCK -Force

    # Archive result
    $archive = Join-Path $OUTBOX "$($id)_result.md"
    if (Test-Path $result) {
        Copy-Item $result $archive -Force
    }

    return $true
}

# Main loop
foreach ($ticket in $TICKETS) {
    # Check for human gate BEFORE dispatch
    if ($ticket.gate -and $ticket.gate_msg) {
        Write-Host "`n*** HUMAN GATE ***" -ForegroundColor Magenta
        Write-Host $ticket.gate_msg -ForegroundColor Magenta
        $response = Read-Host "Type 'continue' to proceed, 'skip' to skip, or 'stop' to halt"
        if ($response -eq "stop") {
            Write-Host "Pipeline halted by human." -ForegroundColor Red
            break
        }
        if ($response -eq "skip") {
            Write-Host "Skipping $($ticket.id)" -ForegroundColor Yellow
            continue
        }
    }

    $success = Dispatch-Ticket $ticket
    if (-not $success) {
        Write-Host "Ticket $($ticket.id) failed. Pipeline halted." -ForegroundColor Red
        break
    }

    Write-Host "Ticket $($ticket.id) dispatched successfully." -ForegroundColor Green
}

Write-Host "`nPipeline complete." -ForegroundColor Cyan
