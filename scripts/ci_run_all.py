"""ci_run_all.py — run pipeline per league + dodaj formę + generuj team_profiles.json."""
import os, sys, json, csv, subprocess, requests
from collections import defaultdict

TOKEN  = os.environ.get("TOKEN", "")
SERVER = os.environ.get("SERVER", "https://betsedge.pl").rstrip("/")

LEAGUES = ["fr_laf_w","fr_lam","de_bl_w","de_bl_m",
           "be_lvl_w","be_lvl_m","fi_ml_w","fi_ml_m","ro_a1_w","ro_a1_m"]

ROLE_WEIGHTS = {"S":1.25,"OPP":1.20,"OH":1.10,"MB":1.00,"L":0.90,"UNKNOWN":1.00}

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
        form[team] = {"win_rate_last5":round(wr5,3), "form_trend":round(trend,3), "games_total":n}
    return form

# ── RUN PIPELINE ──────────────────────────────────────────────

def run_pipeline_liga(liga):
    """Uruchom run_pipeline_v3.py dla jednej ligi."""
    input_dir  = f"data/{liga}"
    output_dir = f"data/{liga}"

    if not os.path.exists(f"{input_dir}/players_raw.csv"):
        print(f"  {liga}: brak players_raw.csv — pomijam")
        return None

    matches_path = f"{input_dir}/matches_with_odds.csv"
    if not os.path.exists(matches_path):
        matches_path = f"{input_dir}/matches.csv"
    result = subprocess.run(
        [sys.executable, "scripts/run_pipeline_v3.py",
         "--input", input_dir, "--output", output_dir,
         "--matches", matches_path],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        print(f"  {liga}: pipeline ERROR\n{result.stderr[-300:]}")
        return None

    # Wczytaj pipeline_output.csv → zbuduj uproszczony profil
    output_path = f"{output_dir}/pipeline_output.csv"
    if not os.path.exists(output_path):
        print(f"  {liga}: brak pipeline_output.csv")
        return None

    rows = list(csv.DictReader(open(output_path, encoding="utf-8-sig")))
    print(f"  {liga}: {len(rows)} wierszy w pipeline_output")
    return rows

# ── BUILD PROFILES FROM PIPELINE OUTPUT ──────────────────────

def build_profiles_from_output(liga, rows):
    """Zbuduj team profiles ze szczegółów pipeline."""
    teams = {}
    for row in rows:
        team = row.get("team_name","").strip()
        if not team: continue
        if team not in teams:
            teams[team] = {"tis_typical": 0, "roster": {}}
        # Dodaj zawodnika do rosteru
        player = row.get("player_name","").strip()
        if player:
            try:
                pis = float(row.get("pis_rolling", row.get("pis", 0)) or 0)
            except: pis = 0
            pos = row.get("position","UNKNOWN")
            try: num = int(float(row.get("player_no",0)))
            except: num = None
            teams[team]["roster"][player] = {
                "number":      num,
                "position":    pos,
                "pis_rolling": round(pis, 2),
                "role_weight": ROLE_WEIGHTS.get(pos, 1.0),
                "games_played": int(float(row.get("games_played", row.get("games",0)) or 0)),
                "start_rate":  round(float(row.get("start_rate",0) or 0), 3),
            }

    # Oblicz TIS per drużyna
    for team, data in teams.items():
        tis = sum(p["pis_rolling"] * p["role_weight"] for p in data["roster"].values())
        data["tis_typical"] = round(tis, 2)

    return teams

# ── MAIN ──────────────────────────────────────────────────────

print("=== BetEdge CI Pipeline ===")
os.makedirs("data/predictions", exist_ok=True)

all_profiles = {}

for liga in LEAGUES:
    print(f"\n[{liga.upper()}]")
    rows = run_pipeline_liga(liga)

    if rows:
        profiles = build_profiles_from_output(liga, rows)
    else:
        # Fallback: wczytaj stary team_profiles.json jeśli istnieje
        old_path = "data/predictions/team_profiles.json"
        if os.path.exists(old_path):
            old = json.load(open(old_path))
            profiles = old.get(liga, {})
            print(f"  {liga}: używam starego profilu (fallback)")
        else:
            profiles = {}

    # Dodaj formę
    form_data = calc_form(liga)
    matched = 0
    for team in profiles:
        fd = form_data.get(team)
        if not fd:
            for fn, fv in form_data.items():
                if fn.lower() in team.lower() or team.lower() in fn.lower():
                    fd = fv; break
        if fd:
            profiles[team]["win_rate_last5"] = fd["win_rate_last5"]
            profiles[team]["form_trend"]     = fd["form_trend"]
            profiles[team]["games_total"]    = fd["games_total"]
            matched += 1
        else:
            profiles[team].setdefault("win_rate_last5", 0.5)
            profiles[team].setdefault("form_trend", 0.0)
            profiles[team].setdefault("games_total", 0)

    all_profiles[liga] = profiles
    print(f"  {liga}: {len(profiles)} drużyn, forma {matched}/{len(profiles)}")

# Zapisz
with open("data/predictions/team_profiles.json", "w", encoding="utf-8") as f:
    json.dump(all_profiles, f, indent=2, ensure_ascii=False)

size = os.path.getsize("data/predictions/team_profiles.json")
total = sum(len(v) for v in all_profiles.values())
print(f"\n✓ team_profiles.json: {total} drużyn, {size} bytes")
