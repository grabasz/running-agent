# 🏃 Running Agent for Claude Desktop

A personal AI running coach powered by Claude Desktop. Analyzes your runs, plans training, generates Garmin workouts, and remembers your context across sessions.

**Works with the free Claude Desktop tier.** No paid API needed.

![demo screenshot placeholder]

## What it does

- 📊 **Analyzes runs** — HR, pace, power, true elevation per km from Strava
- 📅 **Plans training** — Jack Daniels + 80/20 methodology, 5-phase periodization (incl. beginner Run/Walk)
- 🎯 **Multiple distances** — 5K / 10K / HM / Marathon, beginner to advanced
- 🏃 **Race or fitness mode** — prepare for a specific race, or train for general form (with virtual time trials)
- 🌐 **Multilingual** — pick your language, Claude responds in it
- 💾 **Generates Garmin workouts** — ready-to-import JSON with proper structure
- 🌤️ **Checks weather** — affects training advice and race-day strategy
- 🧠 **Remembers context** — VDOT, races, goals, groups persist across sessions
- 🏁 **Race strategy** — tailored taper and pacing for every event

---

## 📋 Prerequisites

- **Windows 10/11** (PowerShell installer; macOS/Linux see "Manual setup" below)
- **[Claude Desktop](https://claude.ai/download)** — free tier is enough
- **[winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/)** — included by default in Windows 11
- **Strava account** (free)
- **Chrome browser** (for Garmin workout import extension)
- **Garmin account** (optional — only if you want JSON import to your watch)

---

## 🚀 Quick Install

```powershell
# 1. Clone this repo
git clone https://github.com/grabasz/running-agent
cd running-agent

# 2. Run installer
.\install.ps1
```

The installer handles **everything**:
1. Installs Node.js v18+ via winget if missing
2. Installs MCP servers via npm
3. Creates `Documents\running\` folder structure
4. Copies starter files with templates
5. Walks you through Strava API setup
6. Updates `claude_desktop_config.json` (Claude Desktop)
7. Updates `~/.claude/settings.json` (Claude Code)
8. Asks for your name, city, VDOT — fills in starter files

After install:
1. **Restart Claude Desktop** (right-click in system tray → Quit, then reopen)
2. **Set project instructions** ← critical for token saving (see below)
3. Type in Claude: **"Connect my Strava account"**
4. Try: *"What is my training plan for today?"*

> ⚡ **Token saving — do this before your first session:**
> In Claude Desktop → open your running project → **Project instructions** → paste the contents of `Documents\running\project_instructions.txt`.
> This tells Claude to load only `skills_core.md` + `profile.md` at the start of each session instead of reading all files. Without this, a single question can burn 80% of your token budget.

---

## 📚 Full Step-by-Step Tutorial

### Step 1 — Install Claude Desktop

1. Download from https://claude.ai/download
2. Sign in with your free Anthropic account
3. Verify it works — try a simple chat

### Step 2 — Clone this repo

Open PowerShell in a folder where you want the code:
```powershell
git clone https://github.com/grabasz/running-agent
cd running-agent
```

If you don't have git: [download as ZIP from GitHub](https://github.com/grabasz/running-agent/archive/refs/heads/master.zip), extract, open PowerShell in the folder.

### Step 3 — Run the installer

```powershell
.\install.ps1
```

If you get an execution policy error:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

The installer will:
- Check/install Node.js (you may need to confirm UAC prompts)
- Install MCP servers via npm (takes ~2 minutes)
- Ask interactive questions:
  - Your name
  - Your city
  - City latitude/longitude (for weather)
  - **Preferred language** (English / Polish / other — Claude will speak this language)
  - **Target distance** (5K / 10K / HM / Marathon)
  - **Level** (beginner / intermediate / advanced)
  - **Mode** (race_prep if you have a race date, fitness otherwise)
  - Your current VDOT (leave blank if unknown or beginner)

### Step 4 — Set up Strava API access

You need a free Strava API app to let Claude read your activities.

1. Go to **https://www.strava.com/settings/api**
2. Fill in the form:

   | Field | Value |
   |-------|-------|
   | Application Name | `Running Agent` (or anything) |
   | Category | `Other` |
   | Club | (leave empty) |
   | Website | `http://localhost` |
   | Application Description | `Personal running coach` |
   | Authorization Callback Domain | `localhost` |

3. Click **Create**

You'll see your **Client ID** and **Client Secret**. **You don't need to copy them anywhere** — the MCP server handles OAuth automatically the first time you connect.

### Step 5 — Restart Claude Desktop

**Important:** simply closing the window doesn't fully restart Claude. You need to:

1. Find Claude icon in system tray (bottom-right corner of taskbar)
2. Right-click → **Quit** (or **Exit**)
3. Reopen from Start menu

### Step 6 — Connect Strava

In Claude Desktop, type:
```
Connect my Strava account
```

A browser window will open → log in to Strava → click **Authorize** → done. Tokens are stored locally and persist across sessions.

### Step 7 — Install Garmin workout importer (optional)

Only needed if you want Claude-generated workouts to sync to your Garmin watch.

1. Install Chrome extension: [Garmin Workout Importer](https://chromewebstore.google.com/detail/odgdfpclpfmmemajpmgfipfdfmjgihac)
2. Go to https://connect.garmin.com/modern/workout/create/running
3. Click extension icon → **Import JSON**
4. Pick a file from `Documents\running\garmin_workouts\upcoming\`
5. Save → syncs to your watch automatically

### Step 8 — Customize your context

Edit these files in `Documents\running\`:

1. **`profile.md`** — your running groups, preferred routes, training schedule
2. **`fitness.md`** — current VDOT, race predictors from your watch
3. **`races.md`** — upcoming races and goals
4. **`plan_current.md`** — Claude will help generate this when you ask

You can edit in Notepad, VS Code, anything that handles text.

### Step 9 — First real session

Try these prompts:

```
"Read my running context and tell me today's workout based on my plan"
"Analyze my last run from Strava"
"What's the weather forecast and should I adjust today's training?"
"Generate a Garmin JSON for tomorrow's intervals"
"Update my plan for the next 2 weeks before my goal race"
```

---

## 📁 File structure

```
Documents\running\
├── profile.md              # Who you are, language, level, goals
├── fitness.md              # VDOT, training paces, race predictors, threshold history
├── races.md                # Race calendar, strategies, logistics
├── plan_current.md         # Current training plan
├── volume_log.md           # Weekly mileage log (auto-generated by /volume)
├── groups.md               # Local running groups (loaded only for group sessions)
├── CLAUDE.md               # Claude Code entrypoint — routing rules
├── skills_core.md          # Router: what to load and when (always loaded)
├── skills_activity.md      # Strava analysis logic (loaded for run/lap questions)
├── skills_planning.md      # Planning logic, phases, volume calibration
├── skills_garmin.md        # Garmin running workout JSON spec (loaded only when generating)
├── skills_gym.md           # Garmin strength workout JSON spec (loaded only when generating)
├── garmin_gen.py           # CLI script: generate Garmin JSON without token cost
├── elev_per_km.py          # Elevation per km calculator (used by /run command)
├── scripts\
│   └── weekly_volume.py    # Processes Strava JSON → volume_log.md
├── skills_phases\          # Per-phase training rules (Daniels)
│   ├── phase0_run_walk.md  # Beginner only — Couch-to-5K
│   ├── phase1_base.md
│   ├── phase2_early_quality.md
│   ├── phase3_late_quality.md
│   └── phase4_taper.md
├── .claude\commands\
│   ├── run.md              # /run — show last run as a table
│   └── volume.md           # /volume — update weekly mileage log
└── garmin_workouts\
    ├── upcoming\           # Running JSON workouts ready to import
    ├── gym\                # Strength workout JSON files
    ├── archive\            # Completed workouts (move here after)
    └── templates\          # Reference Garmin JSON structure
```

**Token-saving design:** skills are split into focused files — only load what the question needs:
- `skills_core.md` — slim router, always loaded
- `skills_activity.md` — Strava analysis, loaded for run/lap/stream questions
- `skills_planning.md` — planning logic, loaded for plan/volume questions
- `skills_garmin.md` — running workout JSON reference, loaded only when generating running workouts
- `skills_gym.md` — strength workout JSON reference, loaded only when generating gym workouts

Strava analysis depth is conditional: Walk/Ride → details only; Run easy → +laps; Run quality/race → +laps+streams.

---

## 🔄 Updating to a new version

The repo is the source of truth for framework files (skills, phases, templates).
Your personal data (profile, fitness, races, plan, workouts) stays untouched.

```powershell
# 1. Pull latest from repo
cd path\to\running-agent
git pull

# 2. Preview changes (optional)
.\sync.ps1 -DryRun

# 3. Apply
.\sync.ps1
```

What sync does:
- **Overwrites** framework files (`skills_core.md`, `skills_garmin.md`, `skills_phases/*`, Garmin templates)
- **Preserves** your personal data (`profile.md`, `fitness.md`, `races.md`, `plan_current.md`, `groups.md`)
- **Migrates** legacy file names automatically (`profil.md` -> `profile.md`, old monolithic `skills.md` removed, `faza*.md` removed, etc.)
- **Never touches** your `garmin_workouts/upcoming/` or `archive/`

After sync: **restart Claude Desktop** to pick up the new behavior rules.

---

## 🔧 Manual setup (macOS/Linux or no winget)

If you can't run the installer:

1. **Install Node.js v18+** from https://nodejs.org

2. **Install MCP servers**:
   ```bash
   npm install -g @r-huijts/strava-mcp-server
   npm install -g @modelcontextprotocol/server-memory
   npm install -g @modelcontextprotocol/server-filesystem
   ```

3. **Create folder**: `~/Documents/running/`

4. **Copy starter files** from `starter_files/` to your running folder

5. **Edit `claude_desktop_config.json`** — see `config_template.json` in this repo for the structure

   Config location:
   - **Windows Store install:** `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\`
   - **Windows direct install:** `%APPDATA%\Claude\`
   - **macOS:** `~/Library/Application Support/Claude/`
   - **Linux:** `~/.config/Claude/`

   Or open it from Claude Desktop → Settings → Developer → Edit Config

6. **Restart Claude Desktop**

---

## 🧠 Training methodology

Based on **Jack Daniels' Running Formula** + **80/20 polarized training**.
Adapts to your **target distance** (5K / 10K / HM / Marathon) and **level** (beginner / intermediate / advanced).

### 5 phases
- **Phase 0 — Run/Walk** *(beginners only)*: 8–10 weeks Couch-to-5K, exits when you can run 30 min continuously
- **Phase I — Base** (foundation): Easy + Strides, volume building
- **Phase II — Early Quality**: R-pace + M-pace (parameters vary by distance)
- **Phase III — Late Quality**: I-pace + T (parameters vary by distance)
- **Phase IV — Taper**: volume reduction, intensity maintained (length varies by distance)

Detailed rules per phase are in `skills_phases/phaseN_*.md`.

### Weekly structure (4 workouts)
- 2× Easy (E pace)
- 1× Quality accent — rotates: Intervals, Threshold, Reps+Strides, Hills, Fartlek, Tempo
- 1× Long Run

### Taper length by distance
| Distance | Taper |
|----------|-------|
| 5K | 5–7 days |
| 10K | 7 days |
| HM | 10 days |
| Marathon | 14–21 days |

Last day: ONE shakeout run (15-20 min + strides + 1× 1min @ race pace).
**Never 4 REST days in a row** during taper.

### Race vs fitness mode
- **race_prep** — phases count backwards from race date
- **fitness** — no race? Cycle ends with a virtual time trial (e.g. parkrun or solo TT) → updates VDOT → starts new cycle

VDOT zones auto-calculated from race or test results, updated after every threshold workout.

---

## 🔌 MCP servers

| Server | Package | Purpose |
|--------|---------|---------|
| Strava | `@r-huijts/strava-mcp-server` | Activity data, splits, HR, power streams |
| Memory | `@modelcontextprotocol/server-memory` | Persistent knowledge graph |
| Filesystem | `@modelcontextprotocol/server-filesystem` | Read/write running files |
| Weather | Open-Meteo (built-in to Claude) | Native Celsius forecasts |

---

## 🛡️ Privacy

The `.gitignore` excludes all personal data:
- `profile.md`, `fitness.md`, `races.md`, `plan_current.md`, `groups.md`
- `garmin_workouts/upcoming/`, `garmin_workouts/archive/`

Only `skills_core.md`, `skills_garmin.md`, `skills_phases/`, templates, and the installer are tracked. **Safe to fork and push your customized version**.

---

## 🐛 Troubleshooting

**"npx not recognized" after install**
- Close PowerShell and reopen — PATH needs to refresh

**"Could not attach to MCP server" in Claude Desktop**
- Check logs at `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\logs\`
- Most common: wrong path in filesystem config, missing folder, or npm install failed

**Strava: "Login failed: 429 Too Many Requests"**
- Wait 30-60 minutes — Strava rate-limited you
- Make sure you're authorizing through the browser window, not pasting credentials

**Polish/special chars show as garbage in Garmin**
- Claude handles this automatically using `\uXXXX` escapes — should not happen
- If it does, regenerate the JSON

---

## 🤝 Contributing

PRs welcome! Ideas:
- macOS/Linux install script
- Support for Polar/Suunto/COROS workout formats
- Google Calendar integration for race scheduling
- Garmin MCP integration (when Cloudflare situation improves)

---

## 📜 License

MIT — fork it, customize it, share it.

---

## 🙏 Credits

- **Jack Daniels** — for the running formula
- **r-huijts** — Strava MCP server
- **Anthropic** — Claude and MCP protocol
- **Open-Meteo** — free weather data
