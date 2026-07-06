# ============================================================
# Running Agent for Claude Desktop — Installer v2.0
# https://github.com/grabasz/running-agent
# ============================================================
# What this does:
#   1. Installs Node.js via winget (if not present)
#   2. Installs MCP servers via npm
#   3. Creates folder structure under Documents\running
#   4. Copies starter files (profile, fitness, races, plan, skills)
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

$TOTAL_STEPS = 9

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
    "@modelcontextprotocol/server-filesystem",
    "@etweisberg/garmin-connect-mcp",
    "@playwright/mcp",
    "open-meteo-mcp-server"
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
Write-Info "Garmin MCP login uses Playwright — Chrome/Edge must be installed (standard on Windows)"

# ============================================================
# STEP 3 — Create folder structure
# ============================================================
Write-Step 3 $TOTAL_STEPS "Creating folder structure at: $InstallPath"

$folders = @(
    $InstallPath,
    "$InstallPath\skills_phases",
    "$InstallPath\garmin_workouts",
    "$InstallPath\garmin_workouts\upcoming",
    "$InstallPath\garmin_workouts\gym",
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

# Copy the ENTIRE starter_files tree (skills, .claude\commands, db\, scripts\,
# garmin_workouts\, dashboard, .streamlit). Existing files are never overwritten
# (user data safe) — use sync.ps1 to update framework files later.
$copied = 0; $skipped = 0
foreach ($item in (Get-ChildItem $starterDir -Recurse -File -Force)) {
    $rel = $item.FullName.Substring($starterDir.Length + 1)
    $dst = Join-Path $InstallPath $rel
    $dstDir = Split-Path -Parent $dst
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
    if (-not (Test-Path $dst)) {
        Copy-Item $item.FullName $dst -Force
        $copied++
    } else {
        $skipped++
    }
}
Write-Info "Copied: $copied file(s), skipped (already exist): $skipped"
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
            command = "cmd"
            args    = @("/c", "npx", "-y", "@r-huijts/strava-mcp-server")
        }
        "memory" = [PSCustomObject]@{
            command = "cmd"
            args    = @("/c", "npx", "-y", "@modelcontextprotocol/server-memory")
        }
        "filesystem" = [PSCustomObject]@{
            command = "cmd"
            args    = @("/c", "npx", "-y", "@modelcontextprotocol/server-filesystem", $InstallPath)
        }
        "garmin" = [PSCustomObject]@{
            command = "cmd"
            args    = @("/c", "npx", "-y", "@etweisberg/garmin-connect-mcp")
        }
        "playwright" = [PSCustomObject]@{
            command = "cmd"
            args    = @("/c", "npx", "-y", "@playwright/mcp")
        }
        "weather" = [PSCustomObject]@{
            command = "cmd"
            args    = @("/c", "npx", "-y", "open-meteo-mcp-server")
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
# STEP 7 — Create project .mcp.json (Claude Code MCP config)
# ============================================================
Write-Step 7 $TOTAL_STEPS "Creating project .mcp.json (Claude Code MCP config)..."

# Claude Code reads MCP servers from <project>\.mcp.json (not settings.json).
$mcpJsonPath = Join-Path $InstallPath ".mcp.json"

if (Test-Path $mcpJsonPath) {
    try {
        $mcpConfig = Get-Content $mcpJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Warn "Could not parse existing .mcp.json: $_ — leaving it untouched"
        $mcpConfig = $null
    }
} else {
    $mcpConfig = [PSCustomObject]@{ mcpServers = [PSCustomObject]@{} }
}

if ($mcpConfig) {
    if (-not ($mcpConfig.PSObject.Properties.Name -contains "mcpServers")) {
        $mcpConfig | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{})
    }

    $ccServers = @{
        "strava"     = [PSCustomObject]@{ command = "npx"; args = @("-y", "@r-huijts/strava-mcp-server") }
        "memory"     = [PSCustomObject]@{ command = "npx"; args = @("-y", "@modelcontextprotocol/server-memory") }
        "filesystem" = [PSCustomObject]@{ command = "npx"; args = @("-y", "@modelcontextprotocol/server-filesystem", $InstallPath) }
        "garmin"     = [PSCustomObject]@{ command = "npx"; args = @("-y", "@etweisberg/garmin-connect-mcp") }
        "playwright" = [PSCustomObject]@{ command = "npx"; args = @("-y", "@playwright/mcp") }
        "weather"    = [PSCustomObject]@{ command = "npx"; args = @("-y", "open-meteo-mcp-server") }
    }

    foreach ($key in $ccServers.Keys) {
        if ($mcpConfig.mcpServers.PSObject.Properties.Name -contains $key) {
            Write-Info "Skipping '$key' (already in .mcp.json)"
        } else {
            $mcpConfig.mcpServers | Add-Member -MemberType NoteProperty -Name $key -Value $ccServers[$key]
            Write-Info "Added: $key"
        }
    }

    $mcpConfig | ConvertTo-Json -Depth 10 | Set-Content $mcpJsonPath -Encoding UTF8
    Write-OK "Project .mcp.json ready: $mcpJsonPath"
}

# ============================================================
# STEP 8 — First run setup: collect user data
# ============================================================
Write-Step 8 $TOTAL_STEPS "Initial profile setup..."

Write-Host ""
Write-Host "   Let's fill in your basic profile so Claude knows who you are." -ForegroundColor White
Write-Host "   (You can skip any field and edit the files later)" -ForegroundColor Gray
Write-Host ""

$name      = Read-Host "   Your name"
$city      = Read-Host "   Your city"
$lat       = Read-Host "   City latitude (for weather, e.g. 50.0647 for Krakow)"
$lon       = Read-Host "   City longitude (e.g. 19.9450 for Krakow)"
$language  = Read-Host "   Preferred language (English / Polish / other) [English]"
if (-not $language) { $language = "English" }
$tempUnit  = Read-Host "   Temperature unit (Celsius / Fahrenheit) [Celsius]"
if (-not $tempUnit) { $tempUnit = "Celsius" }
$distance  = Read-Host "   Target distance (5K / 10K / HM / Marathon) [10K]"
if (-not $distance) { $distance = "10K" }
$level     = Read-Host "   Level (beginner / intermediate / advanced) [intermediate]"
if (-not $level) { $level = "intermediate" }
$mode      = Read-Host "   Mode (race_prep / fitness) [fitness]"
if (-not $mode) { $mode = "fitness" }
$vdot      = Read-Host "   Your current VDOT (leave blank if unknown / beginner — check runsmartproject.com)"

# Update profile.md
$profilePath = Join-Path $InstallPath "profile.md"
if (Test-Path $profilePath) {
    $profileContent = Get-Content $profilePath -Raw
    if ($name)     { $profileContent = $profileContent -replace "\[Your Name\]", $name }
    if ($city)     { $profileContent = $profileContent -replace "\[City\]", $city }
    if ($language) { $profileContent = $profileContent -replace "\[English / Polish / other\]", $language }
    if ($tempUnit) { $profileContent = $profileContent -replace "\[Celsius / Fahrenheit\]", $tempUnit }
    if ($distance) { $profileContent = $profileContent -replace "\[5K / 10K / HM / Marathon\]", $distance }
    if ($level)    { $profileContent = $profileContent -replace "\[beginner / intermediate / advanced\]", $level }
    if ($mode)     { $profileContent = $profileContent -replace "\[race_prep / fitness\]", $mode }
    Set-Content $profilePath $profileContent -Encoding UTF8
    Write-Info "Updated profile: language=$language, distance=$distance, level=$level, mode=$mode"
}

# Update skills_core.md with city coordinates
if ($lat -and $lon) {
    $skillsPath = Join-Path $InstallPath "skills_core.md"
    if (Test-Path $skillsPath) {
        $skills = Get-Content $skillsPath -Raw
        $skills = $skills -replace "latitude, longitude", "$lat, $lon"
        Set-Content $skillsPath $skills -Encoding UTF8
        Write-Info "Updated weather coordinates: $lat, $lon"
    }
}

# Update fitness.md with VDOT (only the VDOT line, not the table headers)
if ($vdot) {
    $fitnessPath = Join-Path $InstallPath "fitness.md"
    if (Test-Path $fitnessPath) {
        $fitness = Get-Content $fitnessPath -Raw
        $fitness = $fitness -replace "\*\*\[value — or: unknown \(beginner\)\]\*\*", "**$vdot**"
        Set-Content $fitnessPath $fitness -Encoding UTF8
        Write-Info "Updated VDOT: $vdot"
    }
}

Write-OK "Profile setup complete"

# Save install path so sync.ps1 knows where to sync next time
$pathFile = Join-Path $scriptDir ".install_path"
Set-Content $pathFile $InstallPath -Encoding UTF8
Write-Info "Install path saved to .install_path (sync.ps1 will use this automatically)"

# ============================================================
# STEP 9 — Python dependencies + database init
# ============================================================
Write-Step 9 $TOTAL_STEPS "Installing Python dependencies + initializing database..."

$pythonCmd = $null
foreach ($candidate in @("python", "py", "python3")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pythonCmd = $candidate
        break
    }
}

if (-not $pythonCmd) {
    Write-Host "   ! Python not found in PATH. Skills (/run, /silownia, /volume) need Python 3.10+." -ForegroundColor Yellow
    Write-Host "     Install from https://python.org, then run:" -ForegroundColor Gray
    Write-Host "       pip install -r `"$InstallPath\scripts\requirements.txt`" -r `"$InstallPath\db\requirements.txt`"" -ForegroundColor Cyan
    Write-Host "       python `"$InstallPath\db\init_db.py`"" -ForegroundColor Cyan
} else {
    foreach ($reqFile in @("scripts\requirements.txt", "db\requirements.txt")) {
        $reqPath = Join-Path $InstallPath $reqFile
        if (Test-Path $reqPath) {
            Write-Info "pip install -r $reqFile"
            & $pythonCmd -m pip install --quiet -r $reqPath
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "pip install failed for $reqFile. Try manually: $pythonCmd -m pip install -r `"$reqPath`""
            }
        } else {
            Write-Warn "Missing: $reqPath"
        }
    }
    Write-OK "Python dependencies installed"

    # Initialize SQLite database (runs, gym, planned workouts, body state...)
    $dbFile = Join-Path $InstallPath "db\data.db"
    if (Test-Path $dbFile) {
        Write-Info "Database already exists: $dbFile (skipping init)"
    } else {
        & $pythonCmd (Join-Path $InstallPath "db\init_db.py")
        if ($LASTEXITCODE -eq 0) {
            Write-OK "Database initialized: $dbFile"
        } else {
            Write-Warn "DB init failed. Try manually: $pythonCmd `"$InstallPath\db\init_db.py`""
        }
    }
    Write-Info "Optional cloud sync (Turso) — see db\README.md (db\.env with credentials)"
}

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
Write-Host "      Windows Store: right-click Claude in taskbar -> Quit" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   2. Set up PROJECT INSTRUCTIONS in Claude Desktop (critical for token saving!)" -ForegroundColor Yellow
Write-Host "      Claude Desktop -> your project -> Project instructions" -ForegroundColor Gray
Write-Host "      Paste the contents of: $InstallPath\project_instructions.txt" -ForegroundColor Cyan
Write-Host "      (Tells Claude to load only skills_core.md + profile.md per session)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   3. Connect Strava — type this in Claude Desktop:" -ForegroundColor Gray
Write-Host "      'Connect my Strava account'" -ForegroundColor Cyan
Write-Host ""
Write-Host "   4. Fill in your race calendar:" -ForegroundColor Gray
Write-Host "      Edit: $InstallPath\races.md" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   5. Connect Garmin — type this in Claude:" -ForegroundColor Gray
Write-Host "      'garmin-login' (a browser window opens, log in to Garmin Connect)" -ForegroundColor Cyan
Write-Host "      Workouts are uploaded directly via MCP (create-workout + schedule-workout)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   6. Start your first session — say to Claude:" -ForegroundColor Gray
Write-Host "      'What is my training plan for today?'" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Files installed at: $InstallPath" -ForegroundColor White
Write-Host ""
