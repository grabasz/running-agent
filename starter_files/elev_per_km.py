# elev_per_km.py — elevation gain/loss calculator per km
# Claude overwrites dist and alt arrays before each run analysis, then runs:
#   python elev_per_km.py
#
# dist = distance array from Strava streams (meters from start)
# alt  = altitude array from Strava streams (meters above sea level)

dist = []
alt  = []

n = len(dist)
if n == 0:
    print("No data — populate dist and alt arrays first")
    exit(1)

total_km = int(dist[-1] / 1000) + 1

for km in range(1, total_km + 1):
    km_start = (km - 1) * 1000
    km_end   = km * 1000
    up   = 0.0
    down = 0.0
    prev_idx = None
    for i in range(n):
        if dist[i] >= km_start and dist[i] <= km_end:
            if prev_idx is not None:
                diff = alt[i] - alt[prev_idx]
                if diff > 0:
                    up += diff
                elif diff < 0:
                    down += abs(diff)
            prev_idx = i
    if up == 0 and down == 0:
        elev = '--'
    else:
        elev = f'+{up:.0f}m / -{down:.0f}m'
    print(f'{km}: {elev}')
