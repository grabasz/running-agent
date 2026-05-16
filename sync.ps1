# ============================================================
# Running Agent - Sync Script
# ============================================================
# Updates your personal running folder from the repo.
# Repo is the source of truth for framework files (skills, phases).
# Personal data (profile, fitness, races, plan, workouts) is preserved.
#
# Usage:
#   .\sync.ps1                                  # default path
#   .\sync.ps1 -InstallPath "D:\my\running"     # custom path
#   .\sync.ps1 -DryRun                          # preview without changes
# ============================================================

param(
    [string]$TargetDirectory = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$starterDir = Join-Path $scriptDir "starter_files"

# Resolve install path: explicit param > .install_path file > default
if ($TargetDirectory) {
    $InstallPath = $TargetDirectory
} else {
    $pathFile = Join-Path $scriptDir ".install_path"
    if (Test-Path $pathFile) {
        $InstallPath = (Get-Content $pathFile -Raw -Encoding UTF8).Trim()
    } else {
        $InstallPath = "$env:USERPROFILE\Documents\running"
        Write-Host "  No .install_path found - using default: $InstallPath" -ForegroundColor Yellow
    }
}

function Write-Action($verb, $what, $color = "Cyan") {
    $prefix = if ($DryRun) { "[DRY RUN] " } else { "" }
    Write-Host "  $prefix$verb $what" -ForegroundColor $color
}
function Copy-IfReal($src, $dst) {
    if (-not $DryRun) {
        $dstDir = Split-Path -Parent $dst
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        Copy-Item $src $dst -Force
    }
}
function Move-IfReal($src, $dst) {
    if (-not $DryRun) {
        Move-Item $src $dst -Force
    }
}
function Remove-IfReal($path) {
    if (-not $DryRun) {
        Remove-Item $path -Force
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Running Agent - Sync from repo" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Source: $starterDir" -ForegroundColor Gray
Write-Host "  Target: $InstallPath" -ForegroundColor Gray
if ($DryRun) { Write-Host "  Mode:   DRY RUN (no changes will be made)" -ForegroundColor Yellow }
Write-Host ""

if (-not (Test-Path $InstallPath)) {
    Write-Host "  Target folder does not exist. Run install.ps1 first." -ForegroundColor Red
    exit 1
}

# ============================================================
# 1. LEGACY MIGRATION - old Polish file names to English
# ============================================================
Write-Host "[1/4] Checking for legacy Polish file names..." -ForegroundColor Yellow

$legacyMap = @{
    "profil.md"         = "profile.md"
    "forma.md"          = "fitness.md"
    "wyscigy.md"        = "races.md"
    "plan_aktualny.md"  = "plan_current.md"
}

foreach ($old in $legacyMap.Keys) {
    $oldPath = Join-Path $InstallPath $old
    $newPath = Join-Path $InstallPath $legacyMap[$old]
    if (Test-Path $oldPath) {
        if (Test-Path $newPath) {
            Write-Action "SKIP rename:" "$old (target $($legacyMap[$old]) already exists - review manually)" "Yellow"
        } else {
            Write-Action "RENAME:" "$old -> $($legacyMap[$old])" "Green"
            Move-IfReal $oldPath $newPath
        }
    }
}

# Legacy phase files (Polish) - delete, will be replaced with English versions
$legacyPhases = @(
    "skills_phases\faza1_baza.md",
    "skills_phases\faza2_jakosc_wczesna.md",
    "skills_phases\faza3_jakosc_pozna.md",
    "skills_phases\faza4_taper.md"
)
foreach ($legacy in $legacyPhases) {
    $p = Join-Path $InstallPath $legacy
    if (Test-Path $p) {
        Write-Action "DELETE legacy:" $legacy "DarkYellow"
        Remove-IfReal $p
    }
}

# Legacy monolithic skills.md - replaced by skills_core.md + skills_garmin.md
$legacySkills = Join-Path $InstallPath "skills.md"
if (Test-Path $legacySkills) {
    Write-Action "DELETE legacy:" "skills.md (replaced by skills_core.md + skills_garmin.md)" "DarkYellow"
    Remove-IfReal $legacySkills
}

# ============================================================
# 2. FRAMEWORK FILES - always overwritten from repo
# ============================================================
Write-Host ""
Write-Host "[2/4] Updating framework files (skills + phases)..." -ForegroundColor Yellow

$frameworkFiles = @(
    "CLAUDE.md",
    "skills_core.md",
    "skills_activity.md",
    "skills_planning.md",
    "skills_garmin.md",
    "garmin_gen.py",
    "elev_per_km.py",
    "scripts\weekly_volume.py",
    "skills_phases\phase0_run_walk.md",
    "skills_phases\phase1_base.md",
    "skills_phases\phase2_early_quality.md",
    "skills_phases\phase3_late_quality.md",
    "skills_phases\phase4_taper.md",
    "garmin_workouts\templates\REFERENCE_real_garmin_export.json",
    ".claude\commands\run.md",
    ".claude\commands\volume.md"
)

foreach ($file in $frameworkFiles) {
    $src = Join-Path $starterDir $file
    $dst = Join-Path $InstallPath $file
    if (-not (Test-Path $src)) {
        Write-Action "MISSING in repo:" $file "Red"
        continue
    }
    $action = if (Test-Path $dst) { "OVERWRITE" } else { "CREATE   " }
    Write-Action "$action :" $file "Green"
    Copy-IfReal $src $dst
}

# ============================================================
# 3. TEMPLATE FILES - only created if missing (user data preserved)
# ============================================================
Write-Host ""
Write-Host "[3/4] Checking personal data templates..." -ForegroundColor Yellow

$templateFiles = @(
    "profile.md",
    "fitness.md",
    "races.md",
    "plan_current.md",
    "garmin_workouts\upcoming\README.md",
    "garmin_workouts\archive\README.md"
)

foreach ($file in $templateFiles) {
    $src = Join-Path $starterDir $file
    $dst = Join-Path $InstallPath $file
    if (-not (Test-Path $src)) {
        Write-Action "MISSING in repo:" $file "Red"
        continue
    }
    if (Test-Path $dst) {
        Write-Action "PRESERVE:" "$file (your data kept)" "Gray"
    } else {
        Write-Action "CREATE:" "$file (template)" "Green"
        Copy-IfReal $src $dst
    }
}

# ============================================================
# 4. SUMMARY
# ============================================================
Write-Host ""
Write-Host "[4/4] Done." -ForegroundColor Yellow
if ($DryRun) {
    Write-Host ""
    Write-Host "  This was a DRY RUN. No files were changed." -ForegroundColor Yellow
    Write-Host "  Run without -DryRun to apply." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "  Sync complete." -ForegroundColor Green
    Write-Host "  Restart Claude Desktop to pick up framework changes." -ForegroundColor Gray
}
Write-Host ""
