"""
ci_run_all.py — generuj team_profiles.json bez run_pipeline_v3.py
Używa tego samego kodu co colab_export_profiles.py (działa w Colabie).
"""
import os, sys, json, csv, requests
from collections import defaultdict

TOKEN  = os.environ.get("TOKEN", "")
SERVER = os.environ.get("SERVER", "https://betsedge.pl").rstrip("/")

LEAGUES = ["fr_laf_w","fr_lam","de_bl_w","de_bl_m",
           "be_lvl_w","be_lvl_m","fi_ml_w","fi_ml_m","ro_a1_w","ro_a1_m"]

ROLE_WEIGHTS = {"S":1.25,"OPP":1.20,"OH":1.10,"MB":1.00,"L":0.90,"UNKNOWN":1.00}

# ── POSITION MAP LOOKUP ───────────────────────────────────────

_position_map = {}

def load_position_map():
    global _position_map
    try:
        token = TOKEN or "aGhxmskexPrJxV1sWOfzLLNRqKKa9XFlNaZxzsutEWk"
        r = requests.get(f"{SERVER}/download.php?liga=predictions&file=position_map.json",
                         headers={"X-Auth-Token": token}, timeout=20)
        if r.status_code == 200:
            _position_map = r.json()
            total = sum(len(t.get("players",{})) for lg in _position_map.values() for t in lg.values())
            print(f"  position_map loaded: {total} zawodników")
        else:
            _position_map = {}
            print(f"  position_map not available ({r.status_code}) — using heuristics")
    except Exception as e:
        _position_map = {}
        print(f"  position_map error: {e} — using heuristics")

def get_position(liga, team_name, player_name):
    if not _position_map: return None
    import unicodedata
    def norm(s):
        return unicodedata.normalize("NFD", (s or "").lower()).encode("ascii","ignore").decode().strip()
    liga_data = _position_map.get((liga or "").lower(), {})
    if not liga_data: return None
    team_data = liga_data.get(team_name)
    if not team_data:
        tn = norm(team_name)
        for k, v in liga_data.items():
            kn = norm(k)
            if kn in tn or tn in kn or (kn.split() and kn.split()[0] in tn):
                team_data = v; break
    if not team_data or "players" not in team_data: return None
    pn = norm(player_name)
    for name, data in team_data["players"].items():
        nn = norm(name)
        if nn == pn: return data["position"]
        parts_a, parts_b = pn.split(), nn.split()
        if parts_a and parts_b and parts_a[-1] == parts_b[-1] and len(parts_a[-1]) > 2:
            return data["position"]
        if nn in pn or pn in nn: return data["position"]
    return None

def infer_position_v2(att, blk, srv, rec, pts, is_lib=False):
    """Ulepszona heurystyka — fallback gdy brak position_map."""
    if is_lib: return "L"
    if pts < 0.5 and att < 0.5 and rec > 3.0: return "L"
    if att < 1.5 and pts < 3.0 and blk < 0.5: return "S"
    if blk >= 1.0 and rec < 1.5: return "MB"
    if att >= 5.0 and rec < 2.0: return "OPP"
    if att >= 2.0 and rec >= 2.0: return "OH"
    if att >= 4.0: return "OPP"
    if blk >= 0.8: return "MB"
    if att >= 1.5: return "OH"
    return "UNKNOWN"

# ── POSITION INFERENCE ────────────────────────────────────────

def infer_position(att, blk, srv, rec, pts):
    if pts < 1.0 and rec > 2.0: return "L"
    if srv > 0.8 and att < 3.0 and blk < 0.8: return "S"
    if att > 3.0 and rec < 1.5 and blk < 1.5: return "OPP"
    if blk > 0.5 and rec < 2.0: return "MB"
    if att > 1.0 and rec > 0.5: return "OH"
    if att > 1.5: return "OPP"
    if blk > 0.3: return "MB"
    if pts > 1.0: return "OH"
    return "UNKNOWN"

def compute_pis(att, srv_ace, blk, att_err, srv_err, rec_pos):
    err = att_err + srv_err
    return max(round(att + srv_ace*1.5 + blk*1.2 - err*0.5 + rec_pos*0.3, 2), 0.0)

# ── BUILD PROFILES FROM players_raw.csv ──────────────────────

def build_profiles_from_csv(liga):
    path = f"data/{liga}/players_raw.csv"
    if not os.path.exists(path):
        print(f"  {liga}: brak players_raw.csv")
        return {}

    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if not rows:
        return {}

    # Grupuj per (team, player)
    player_stats = defaultdict(lambda: defaultdict(float))
    player_games  = defaultdict(set)
    player_number = {}

    for row in rows:
        team   = row.get("team_name","").strip()
        player = row.get("player_name","").strip()
        mid    = row.get("match_id","").strip()
        if not team or not player: continue

        key = (team, player)
        player_number[key] = row.get("player_no","")

        def g(col): 
            try: return float(row.get(col,0) or 0)
            except: return 0.0

        player_stats[key]["att_pts"]  += g("att_pts")
        player_stats[key]["srv_ace"]  += g("srv_ace")
        player_stats[key]["blocks"]   += g("blocks")
        player_stats[key]["att_err"]  += g("att_err")
        player_stats[key]["srv_err"]  += g("srv_err")
        player_stats[key]["rec_pos"]  += g("rec_pos")
        player_stats[key]["total_pts"]+= g("total_pts")
        if mid: player_games[key].add(mid)

    # Per drużyna → roster
    teams = defaultdict(dict)
    for (team, player), stats in player_stats.items():
        games = max(len(player_games[(team,player)]), 1)
        att   = stats["att_pts"]  / games
        srv   = stats["srv_ace"]  / games
        blk   = stats["blocks"]   / games
        aerr  = stats["att_err"]  / games
        serr  = stats["srv_err"]  / games
        rec   = stats["rec_pos"]  / games
        pts   = stats["total_pts"]/ games

        # Lookup oficjalnej pozycji (z position_map), fallback heurystyka
        pos_official = get_position(liga, team, player)
        pos = pos_official if pos_official else infer_position_v2(att, blk, srv, rec, pts, is_lib)
        pis = compute_pis(att, srv, blk, aerr, serr, rec)

        try: num = int(float(player_number[(team,player)]))
        except: num = None

        teams[team][player] = {
            "number":      num,
            "position":    pos,
            "pis_rolling": pis,
            "role_weight": ROLE_WEIGHTS.get(pos, 1.0),
            "games_played": games,
            "start_rate":  1.0,
        }

    # Oblicz TIS + ogranicz do top 7 + 1 libero
    profiles = {}
    for team, roster in teams.items():
        liberos   = {p:d for p,d in roster.items() if d["position"]=="L"}
        non_lib   = {p:d for p,d in roster.items() if d["position"]!="L"}
        top7      = dict(sorted(non_lib.items(), key=lambda x:-x[1]["pis_rolling"])[:7])
        top_lib   = dict(sorted(liberos.items(), key=lambda x:-x[1]["pis_rolling"])[:1])
        final_roster = {**top7, **top_lib}
        tis = sum(p["pis_rolling"]*p["role_weight"] for p in final_roster.values())
        profiles[team] = {"tis_typical": round(tis,2), "roster": final_roster}

    print(f"  {liga}: {len(profiles)} drużyn")
    return profiles

# ── FORM CALCULATION ──────────────────────────────────────────

def calc_form(liga):
    path = f"data/{liga}/matches_with_odds.csv"
    if not os.path.exists(path):
        return {}
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    rows.sort(key=lambda m: m.get("match_datetime",""))
    team_results = defaultdict(list)
    for m in rows:
        home = m.get("home_team","").strip()
        away = m.get("away_team","").strip()
        if not home or not away: continue
        try:
            hs  = int(float(m.get("home_sets",0) or 0))
            aws = int(float(m.get("away_sets",0) or 0))
        except: continue
        if hs+aws==0: continue
        team_results[home].append(hs>aws)
        team_results[away].append(aws>hs)
    form = {}
    for team, results in team_results.items():
        n = len(results)
        last5 = results[-5:] if n>=5 else results
        wr5   = sum(last5)/len(last5)
        trend = (sum(results[-3:])/3 - sum(results[-5:-3])/2) if n>=5 else 0.0
        form[team] = {"win_rate_last5":round(wr5,3),"form_trend":round(trend,3),"games_total":n}
    return form


# ── LAST LINEUP ───────────────────────────────────────────────

def calc_last_lineup(players_raw_rows, matches_rows=None):
    """Per drużyna: znajdź ostatni mecz i zwróć skład + stats + opponent."""
    # Zbuduj słownik mid → opponent
    mid_opponent = {}
    mid_date = {}
    if matches_rows:
        for m in matches_rows:
            mid = m.get("match_id","").strip()
            home = m.get("home_team","").strip()
            away = m.get("away_team","").strip()
            dt   = m.get("match_datetime","").strip()
            if mid:
                mid_opponent[mid] = {"home": home, "away": away}
                mid_date[mid] = dt

    team_matches = defaultdict(lambda: defaultdict(list))
    for row in players_raw_rows:
        team = row.get("team_name","").strip()
        mid  = row.get("match_id","").strip()
        if team and mid:
            team_matches[team][mid].append(row)

    result = {}
    ROLE_W = {"S":1.25,"OPP":1.20,"OH":1.10,"MB":1.00,"L":0.90,"UNKNOWN":1.0}

    for team, matches in team_matches.items():
        if not matches: continue
        sorted_mids = sorted(matches.keys(), key=lambda x: int(x) if x.isdigit() else 0)
        last_mid = sorted_mids[-1]
        last_players = matches[last_mid]

        match_date = last_players[0].get("match_datetime","") if last_players else ""

        starters = []
        for p in last_players:
            name   = p.get("player_name","").strip()
            number = p.get("player_no","")
            is_lib = str(p.get("libero","")).strip().upper() == "L"
            try: s1 = int(float(p.get("set1",0) or 0))
            except: s1 = 0
            if s1 == 0 and not is_lib: continue

            def _f(k): 
                try: return float(p.get(k,0) or 0)
                except: return 0.0

            pis_match = round(
                _f("att_pts")*1.0 + _f("blocks")*1.3 +
                _f("srv_ace")*1.2 + _f("srv_err")*(-0.8) + _f("att_err")*(-0.8), 2)

            pos = p.get("position","UNKNOWN")
            starters.append({
                "name":     name,
                "number":   int(number) if str(number).isdigit() else 0,
                "position": pos,
                "pis_match": pis_match,
                "pts":      int(_f("total_pts")),
                "srv_ace":  int(_f("srv_ace")),
                "att_pts":  int(_f("att_pts")),
                "blocks":   int(_f("blocks")),
                "libero":   is_lib,
                "start_rate_last3": 0.0,
            })

        # start_rate_last3
        last_3 = sorted_mids[-3:] if len(sorted_mids) >= 3 else sorted_mids
        for s in starters:
            cnt = 0
            for mid in last_3:
                for pp in matches[mid]:
                    if pp.get("player_name","").strip() == s["name"]:
                        try: s1_v = int(float(pp.get("set1",0) or 0))
                        except: s1_v = 0
                        is_l = str(pp.get("libero","")).strip().upper() == "L"
                        if s1_v > 0 or is_l:
                            cnt += 1
            s["start_rate_last3"] = round(cnt / len(last_3), 2)

        tis_match = sum(
            s["pis_match"] * ROLE_W.get(s["position"],1.0) for s in starters)

        # Znajdź przeciwnika
        opponent = ""
        if last_mid in mid_opponent:
            opp_data = mid_opponent[last_mid]
            if opp_data["home"] == team:
                opponent = opp_data["away"]
            else:
                opponent = opp_data["home"]
        if last_mid in mid_date and not match_date:
            match_date = mid_date[last_mid]

        result[team] = {
            "match_id":   last_mid,
            "match_date": match_date,
            "opponent":   opponent,
            "starters":   starters,
            "tis_match":  round(tis_match, 1),
            "n_starters": len(starters),
        }
    return result

# ── MAIN ──────────────────────────────────────────────────────

print("=== BetEdge CI Pipeline (standalone) ===")
os.makedirs("data/predictions", exist_ok=True)
load_position_map()

all_profiles = {}

for liga in LEAGUES:
    print(f"\n[{liga.upper()}]")
    profiles = build_profiles_from_csv(liga)

    # Forma
    form_data = calc_form(liga)
    matched = 0
    for team in profiles:
        fd = form_data.get(team)
        if not fd:
            for fn,fv in form_data.items():
                if fn.lower() in team.lower() or team.lower() in fn.lower():
                    fd=fv; break
        if fd:
            profiles[team]["win_rate_last5"] = fd["win_rate_last5"]
            profiles[team]["form_trend"]     = fd["form_trend"]
            profiles[team]["games_total"]    = fd["games_total"]
            matched += 1
        else:
            profiles[team].setdefault("win_rate_last5", 0.5)
            profiles[team].setdefault("form_trend", 0.0)
            profiles[team].setdefault("games_total", 0)

    print(f"  forma: {matched}/{len(profiles)}")
    all_profiles[liga] = profiles

with open("data/predictions/team_profiles.json","w",encoding="utf-8") as f:
    json.dump(all_profiles, f, indent=2, ensure_ascii=False)

total = sum(len(v) for v in all_profiles.values())
size  = os.path.getsize("data/predictions/team_profiles.json")
print(f"\n✓ team_profiles.json: {total} drużyn, {size} bytes")
