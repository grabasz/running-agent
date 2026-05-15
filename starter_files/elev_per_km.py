import sys, json

dist = json.loads(sys.argv[1])
alt = json.loads(sys.argv[2])

n = len(dist)
total_km = int(dist[-1] / 1000) + 1

results = []
for km in range(1, total_km + 1):
    km_start = (km - 1) * 1000
    km_end = km * 1000
    up = 0.0
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
    results.append((km, up, down))

for km, up, down in results:
    if up == 0 and down == 0:
        elev = '--'
    else:
        elev = f'+{up:.0f}m / -{down:.0f}m'
    print(f'{km}: {elev}')
