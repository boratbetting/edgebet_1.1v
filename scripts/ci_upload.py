"""ci_upload.py — upload team_profiles.json + pipeline outputs na serwer."""
import os, requests, time

TOKEN  = os.environ["TOKEN"]
SERVER = os.environ.get("SERVER", "https://betsedge.pl").rstrip("/")

LEAGUES = ["fr_laf_w","fr_lam","de_bl_w","de_bl_m",
           "be_lvl_w","be_lvl_m","fi_ml_w","fi_ml_m","ro_a1_w","ro_a1_m"]

def upload(liga, fname, path):
    if not os.path.exists(path):
        print(f"  - {liga}/{fname}: brak pliku")
        return False
    with open(path, "rb") as f:
        r = requests.post(
            f"{SERVER}/upload.php?liga={liga}&file={fname}",
            headers={"X-Auth-Token": TOKEN},
            data=f.read(), timeout=60
        )
    ok = r.status_code == 200
    print(f"  {'✓' if ok else '✗'} {liga}/{fname}: {r.status_code}")
    return ok

# team_profiles.json — najważniejszy
upload("predictions", "team_profiles.json", "data/predictions/team_profiles.json")

# pipeline outputs per liga
for liga in LEAGUES:
    upload(liga, "pipeline_output.csv", f"data/{liga}/pipeline_output.csv")
    time.sleep(0.2)

print("\nUpload complete.")
