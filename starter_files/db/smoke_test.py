"""Smoke test — sample queries the dashboard / MCP server will use."""
import sys
sys.path.insert(0, ".")
import api  # type: ignore

print("\n" + "="*60)
print("SMOKE TEST — realne pytania do dashboardu / Claude'a")
print("="*60)

with api.connect() as conn:

    print("\n[1] VDOT aktualny:")
    v = api.vdot.current(conn)
    print(f"  VDOT {v['vdot']} | T-pace {v['t_pace_sec']//60}:{v['t_pace_sec']%60:02d}/km | data {v['date']}")

    print("\n[2] Progresja VDOT:")
    for h in api.vdot.history(conn, limit=20):
        print(f"  {h['date']}  VDOT {h['vdot']:2d}  T-pace {h['t_pace_sec']//60}:{h['t_pace_sec']%60:02d}/km")

    print("\n[3] Wyscigi nadchodzace:")
    for r in api.races.upcoming(conn):
        t = r['target_time_sec']
        target = f"sub {t//3600}:{(t%3600)//60:02d}" if t else "—"
        print(f"  {r['date']}  {r['name']:35} cel: {target}")

    print("\n[4] PB HM (21.0975 km):")
    pb = api.race_pb(21.0975)
    if pb:
        t = pb['actual_time_sec']
        print(f"  {pb['date']}  {pb['name']}  {t//3600}:{(t%3600)//60:02d}:{t%60:02d}")

    print("\n[5] Progresja BSS (ostatnich 6 setow):")
    for s in api.gym.exercise_progression(conn, exercise="BSS", limit=6):
        side = "/strona" if s['weight_per_side'] else ""
        wt = f"{s['weight_kg']}kg{side}" if s['weight_kg'] else "BW"
        print(f"  {s['date']}  set {s['set_num']}: {s['reps']} reps @ {wt}  ({s['notes'] or ''})")

    print("\n[6] Progresja RDL (ostatnich 6 setow):")
    for s in api.gym.exercise_progression(conn, exercise="RDL", limit=6):
        print(f"  {s['date']}  set {s['set_num']}: {s['reps']} reps @ {s['weight_kg']}kg  ({s['notes'] or ''})")

    print("\n[7] Wolumen tygodniowy (ostatnie 6 tyg):")
    for w in api.weekly_volume.recent(conn, weeks=6):
        trend = f" [{w['trend']}]" if w['trend'] else ""
        print(f"  {w['week_start']}  {w['distance_km']:5.1f} km  | {w['num_runs']} biegi | longest {w['longest_km']:.1f}km{trend}")

    print("\n[8] Stan ciala — ostatnie 14 dni:")
    for b in api.body.state_recent(conn, since="-14 days"):
        p = f"bol {b['pain_0_10']}/10" if b['pain_0_10'] is not None else ""
        d = " DOMS" if b['doms'] else ""
        print(f"  {b['date']}  {b['location']:18} {p}{d}  ({b['notes'] or ''})")

    print("\n[9] Ostatnie sesje silowni:")
    for s in api.gym.sessions_recent(conn, limit=5):
        print(f"  {s['date']}  {s['duration_min'] or '?'} min  | {s['context'] or ''}")

    print("\n[10] BONUS — top exercises by volume (od 2026-01-01):")
    for r in api.gym.top_exercises_by_volume(conn, since="2026-01-01"):
        print(f"  {r['exercise']:30} {int(r['volume_kg']):>6} kg total  ({r['sets']} sets)")

print("\nOK.")
