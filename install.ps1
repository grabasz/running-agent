# ============================================================
# Running Agent for Claude Desktop — Installer v2.0
# https://github.com/[YOUR_USERNAME]/running-agent
# ============================================================
# What this does:
#   1. Installs Node.js via winget (if not present)
#   2. Installs MCP servers via npm
#   3. Creates folder structure under Documents\running
#   4. Copies starter files (profil, forma, wyscigy, plan, skills)
#   5. Copies Garmin workout templates
#   6. Updates claude_desktop_config.json
#   7. Guides through Strava API setup
# ============================================================

param(
    [string]$InstallPath = "$env:USERPROFILE\Documents\running",
    [string]$ClaudeConfigPath = "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json"
)

$ErrorActionPreference = "Stop"

function Write-Step($n, $total, $msg) {
    Write-Host ""
    Write-Host "[$n/$total] $msg" -ForegroundColor Yellow
}
function Write-OK($msg)   { Write-Host "      OK: $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "      $msg" -ForegroundColor Gray }
function Write-Warn($msg) { Write-Host "      WARN: $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "      ERROR: $msg" -ForegroundColor Red }

$TOTAL_STEPS = 7

Clear-Host
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   🏃 Running Agent for Claude Desktop — Installer v2.0" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   This installer will set up your AI running coach." -ForegroundColor White
Write-Host "   Estimated time: 3-5 minutes." -ForegroundColor Gray
Write-Host ""

# ============================================================
# STEP 1 — Node.js via winget
# ============================================================
Write-Step 1 $TOTAL_STEPS "Checking / Installing Node.js..."

$nodeOk = $false
try {
    $nodeVersion = node --version 2>$null
    if ($nodeVersion -match "v(\d+)") {
        $major = [int]$Matches[1]
        if ($major -ge 18) {
            Write-OK "Node.js $nodeVersion already installed"
            $nodeOk = $true
        } else {
            Write-Warn "Node.js $nodeVersion found but v18+ required — upgrading..."
        }
    }
} catch {}

if (-not $nodeOk) {
    Write-Info "Installing Node.js LTS via winget..."
    try {
        winget install --id OpenJS.NodeJS.LTS --silent --accept-source-agreements --accept-package-agreements
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $nodeVersion = node --version 2>$null
        Write-OK "Node.js $nodeVersion installed successfully"
    } catch {
        Write-Err "Failed to install Node.js via winget."
        Write-Host "      Please install manually from https://nodejs.org (v18+)" -ForegroundColor Red
        Write-Host "      Then re-run this installer." -ForegroundColor Red
        exit 1
    }
}

# ============================================================
# STEP 2 — Install MCP servers
# ============================================================
Write-Step 2 $TOTAL_STEPS "Installing MCP servers..."

$mcpPackages = @(
    "@r-huijts/strava-mcp-server",
    "@modelcontextprotocol/server-memory",
    "@modelcontextprotocol/server-filesystem"
)

foreach ($pkg in $mcpPackages) {
    Write-Info "npm install -g $pkg"
    $result = npm install -g $pkg 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK $pkg
    } else {
        Write-Warn "$pkg — check manually if issues arise"
    }
}
Write-Info "Weather MCP (Open-Meteo) is built-in to Claude — no install needed"

# ============================================================
# STEP 3 — Create folder structure
# ============================================================
Write-Step 3 $TOTAL_STEPS "Creating folder structure at: $InstallPath"

$folders = @(
    $InstallPath,
    "$InstallPath\skills_phases",
    "$InstallPath\garmin_workouts",
    "$InstallPath\garmin_workouts\upcoming",
    "$InstallPath\garmin_workouts\archive",
    "$InstallPath\garmin_workouts\templates"
)
foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
        Write-Info "Created: $folder"
    } else {
        Write-Info "Exists:  $folder"
    }
}
Write-OK "Folders ready"

# ============================================================
# STEP 4 — Copy starter files
# ============================================================
Write-Step 4 $TOTAL_STEPS "Copying starter files..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$starterDir = Join-Path $scriptDir "starter_files"

$files = @(
    "profil.md",
    "forma.md",
    "wyscigy.md",
    "plan_aktualny.md",
    "skills.md",
    "skills_phases\phase1_base.md",
    "skills_phases\phase2_early_quality.md",
    "skills_phases\phase3_late_quality.md",
    "skills_phases\phase4_taper.md",
    "garmin_workouts\templates\REFERENCE_real_garmin_export.json",
    "garmin_workouts\upcoming\README.md",
    "garmin_workouts\archive\README.md"
)

foreach ($file in $files) {
    $src = Join-Path $starterDir $file
    $dst = Join-Path $InstallPath $file
    if (Test-Path $src) {
        $dstDir = Split-Path -Parent $dst
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        if (-not (Test-Path $dst)) {
            Copy-Item $src $dst -Force
            Write-Info "Copied: $file"
        } else {
            Write-Info "Skipped (exists): $file"
        }
    } else {
        Write-Warn "Not found in starter_files: $file"
    }
}
Write-OK "Starter files ready"

# ============================================================
# STEP 5 — Strava API setup guide
# ============================================================
Write-Step 5 $TOTAL_STEPS "Strava API Setup"

Write-Host ""
Write-Host "   To connect Claude to your Strava account, you need a free Strava API app." -ForegroundColor White
Write-Host "   This takes about 2 minutes. Here's how:" -ForegroundColor Gray
Write-Host ""
Write-Host "   1. Go to: https://www.strava.com/settings/api" -ForegroundColor Cyan
Write-Host "   2. Fill in the form:" -ForegroundColor Gray
Write-Host "      - Application Name: Running Agent (or anything you like)" -ForegroundColor Gray
Write-Host "      - Category: Other" -ForegroundColor Gray
Write-Host "      - Website: http://localhost" -ForegroundColor Gray
Write-Host "      - Authorization Callback Domain: localhost" -ForegroundColor Gray
Write-Host "   3. Click Create — you'll get a Client ID and Client Secret" -ForegroundColor Gray
Write-Host "   4. The @r-huijts/strava-mcp-server handles OAuth automatically" -ForegroundColor Gray
Write-Host "      Just restart Claude Desktop and type: 'Connect my Strava account'" -ForegroundColor Gray
Write-Host "      A browser window will open for authorization." -ForegroundColor Gray
Write-Host ""

$stravaReady = Read-Host "   Have you already set up your Strava API app? (y/n)"
if ($stravaReady -eq "y") {
    Write-OK "Strava API app ready — connect after Claude Desktop restart"
} else {
    Write-Info "No problem — you can do this later. Follow the steps above when ready."
}

# ============================================================
# STEP 6 — Update claude_desktop_config.json
# ============================================================
Write-Step 6 $TOTAL_STEPS "Updating Claude Desktop config..."

# Detect config path
$configPaths = @(
    $ClaudeConfigPath,
    "$env:LOCALAPPDATA\AnthropicClaude\claude_desktop_config.json",
    "$env:APPDATA\Claude\claude_desktop_config.json"
)
$configFile = $null
foreach ($p in $configPaths) {
    if (Test-Path $p) { $configFile = $p; break }
}

if (-not $configFile) {
    # Try to find it
    $found = Get-ChildItem "$env:LOCALAPPDATA\Packages" -Recurse -Filter "claude_desktop_config.json" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $configFile = $found.FullName }
}

if (-not $configFile) {
    Write-Warn "claude_desktop_config.json not found — creating at default location"
    $configFile = $ClaudeConfigPath
    $configDir = Split-Path -Parent $configFile
    if (-not (Test-Path $configDir)) { New-Item -ItemType Directory -Path $configDir -Force | Out-Null }
    '{"mcpServers":{}}' | Set-Content $configFile -Encoding UTF8
}

Write-Info "Config: $configFile"

try {
    $configRaw = Get-Content $configFile -Raw -Encoding UTF8
    $config = $configRaw | ConvertFrom-Json

    if (-not $config.mcpServers) {
        $config | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{})
    }

    $newServers = @{
        "strava" = [PSCustomObject]@{
            command = "npx"
            args    = @("-y", "@r-huijts/strava-mcp-server")
        }
        "memory" = [PSCustomObject]@{
            command = "npx"
            args    = @("-y", "@modelcontextprotocol/server-memory")
        }
        "filesystem" = [PSCustomObject]@{
            command = "npx"
            args    = @("-y", "@modelcontextprotocol/server-filesystem", $InstallPath)
        }
    }

    foreach ($key in $newServers.Keys) {
        if ($config.mcpServers.PSObject.Properties.Name -contains $key) {
            Write-Info "Skipping '$key' (already in config)"
        } else {
            $config.mcpServers | Add-Member -MemberType NoteProperty -Name $key -Value $newServers[$key]
            Write-Info "Added: $key"
        }
    }

    $config | ConvertTo-Json -Depth 10 | Set-Content $configFile -Encoding UTF8
    Write-OK "Config updated"
} catch {
    Write-Warn "Could not update config automatically: $_"
    Write-Info "Use config_template.json as a reference and update manually"
}

# ============================================================
# STEP 7 — First run setup: collect user data
# ============================================================
Write-Step 7 $TOTAL_STEPS "Initial profile setup..."

Write-Host ""
Write-Host "   Let's fill in your basic profile so Claude knows who you are." -ForegroundColor White
Write-Host "   (You can skip any field and edit the files later)" -ForegroundColor Gray
Write-Host ""

$name    = Read-Host "   Your name"
$city    = Read-Host "   Your city"
$lat     = Read-Host "   City latitude (for weather, e.g. 50.0647 for Krakow)"
$lon     = Read-Host "   City longitude (e.g. 19.9450 for Krakow)"
$vdot    = Read-Host "   Your current VDOT (leave blank if unknown — check runsmartproject.com)"

# Update profil.md
$profilPath = Join-Path $InstallPath "profil.md"
if (Test-Path $profilPath) {
    $profil = Get-Content $profilPath -Raw
    if ($name) { $profil = $profil -replace "\[Twoje Imię i Nazwisko\]", $name }
    if ($city) { $profil = $profil -replace "\[Miasto\]", $city }
    Set-Content $profilPath $profil -Encoding UTF8
}

# Update skills.md with city coordinates
if ($lat -and $lon) {
    $skillsPath = Join-Path $InstallPath "skills.md"
    if (Test-Path $skillsPath) {
        $skills = Get-Content $skillsPath -Raw
        $skills = $skills -replace "latitude, longitude", "$lat, $lon"
        Set-Content $skillsPath $skills -Encoding UTF8
        Write-Info "Updated weather coordinates: $lat, $lon"
    }
}

# Update forma.md with VDOT
if ($vdot) {
    $formaPath = Join-Path $InstallPath "forma.md"
    if (Test-Path $formaPath) {
        $forma = Get-Content $formaPath -Raw
        $forma = $forma -replace "\[wartość\]", $vdot
        Set-Content $formaPath $forma -Encoding UTF8
        Write-Info "Updated VDOT: $vdot"
    }
}

Write-OK "Profile setup complete"

# ============================================================
# DONE
# ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   ✅ Installation complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Next steps:" -ForegroundColor White
Write-Host ""
Write-Host "   1. Restart Claude Desktop (Quit from system tray, reopen)" -ForegroundColor Gray
Write-Host "      Windows Store: right-click Claude in taskbar → Quit" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   2. Connect Strava — type this in Claude Desktop:" -ForegroundColor Gray
Write-Host "      'Connect my Strava account'" -ForegroundColor Cyan
Write-Host ""
Write-Host "   3. Fill in your race calendar:" -ForegroundColor Gray
Write-Host "      Edit: $InstallPath\wyscigy.md" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   4. Install Garmin workout importer for Chrome:" -ForegroundColor Gray
Write-Host "      https://chromewebstore.google.com/detail/odgdfpclpfmmemajpmgfipfdfmjgihac" -ForegroundColor Cyan
Write-Host ""
Write-Host "   5. Start your first session — say to Claude:" -ForegroundColor Gray
Write-Host "      'Read my running context and tell me today's workout'" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Files installed at: $InstallPath" -ForegroundColor White
Write-Host ""
