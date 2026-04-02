"""ci_download.py — pobierz dane z betsedge.pl przed pipeline."""
import os, requests, time

TOKEN  = os.environ["TOKEN"]
SERVER = os.environ.get("SERVER", "https://betsedge.pl").rstrip("/")

LEAGUES = ["fr_laf_w","fr_lam","de_bl_w","de_bl_m",
           "be_lvl_w","be_lvl_m","fi_ml_w","fi_ml_m","ro_a1_w","ro_a1_m"]

FILES = ["players_raw.csv", "matches_with_odds.csv", "matches.csv"]

for liga in LEAGUES:
    os.makedirs(f"data/{liga}", exist_ok=True)
    for fname in FILES:
        r = requests.get(f"{SERVER}/download.php?liga={liga}&file={fname}",
                         headers={"X-Auth-Token": TOKEN}, timeout=30)
        if r.status_code == 200 and len(r.content) > 50:
            open(f"data/{liga}/{fname}", "wb").write(r.content)
            print(f"  ✓ {liga}/{fname}: {r.text.count(chr(10))} lines")
        else:
            print(f"  - {liga}/{fname}: {r.status_code}")
        time.sleep(0.3)

print("\nDownload complete.")
