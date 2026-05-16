# SKILLS CORE — Router (load ONCE per session)

> Universal rules and file map only.
> Activity logic → `skills_activity.md` | Planning logic → `skills_planning.md`

## Language
Read `profile.md` once per session. Use the language from "Preferred language". Never mix languages.

## Dates
Verify via `weather:weather_forecast` → `current.time`. Before any plan: state 3 control dates (first/middle/last) and confirm.

## Weather
Tool: `weather:weather_forecast` (Open-Meteo, timezone=local).
Temperature unit: read from `profile.md → Temperature unit` (default: Celsius). Never mix units in one response.
WMO icons: 0-1=☀️ 2-3=🌤️ 51-67=🌧️ 71-77=❄️ 80-82=🌦️ 95+=⚡
Running effects: >20°C/68°F → +5-8bpm HR | <5°C/41°F → layer up | wind >20km/h → affects pace.

## File map — what to load and when
| File | When |
|------|------|
| `profile.md` | ONCE per session |
| `skills_activity.md` | Analyzing runs, laps, streams, splits, HR, race results |
| `skills_planning.md` | Planning, weekly structure, volume, phases |
| `skills_garmin.md` | Generating Garmin Connect JSON |
| `skills_phases/phaseN_*.md` | Building a plan for a specific phase (N=0–4) |
| `fitness.md` | Analyzing form, computing VDOT paces |
| `races.md` | Races, race strategy |
| `plan_current.md` | Current plan, today/tomorrow/this week |
| `groups.md` | Group training sessions |
| `volume_log.md` | Weekly volume — <7 days old: read it; older: run `/volume` |

## Rule
Do not load a file unless required by the type of question.
Activity logic and planning logic are separate — do not mix in a single load.
