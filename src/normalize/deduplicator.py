
def deduplicate_matches(matches):
    seen = {}
    for m in matches:
        mid = str(m.get("match_id","")).strip()
        if mid and mid not in seen:
            seen[mid] = m
    out = list(seen.values())
    report = {"input_count": len(matches), "output_count": len(out)}
    return out, [], report

def deduplicate_player_stats(players):
    seen = set()
    out = []
    for p in players:
        key = (str(p.get("match_id","")), str(p.get("player_name","")))
        if key not in seen:
            seen.add(key)
            out.append(p)
    report = {"input_count": len(players), "output_count": len(out)}
    return out, [], report
