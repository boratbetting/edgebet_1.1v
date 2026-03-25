
import sys
sys.path.insert(0, "/content/betedge")
import pandas as pd
import numpy as np
import yaml

BASE        = "/content/betedge"
DATA_RAW    = f"{BASE}/data/raw"
DATA_RES    = f"{BASE}/data/results"
CONFIG_PATH = f"{BASE}/configs/params_v1.yaml"

with open(CONFIG_PATH) as f:
    cfg = yaml.safe_load(f)

roll_w  = cfg["rolling"]
role_w  = {k.upper(): v for k, v in cfg["role_weights"].items()}
form_w  = 0.10
tis_w   = 0.02
max_adj = 0.08

matches = pd.read_csv(f"{DATA_RAW}/matches.csv", low_memory=False)
players = pd.read_csv(f"{DATA_RAW}/players_raw.csv", low_memory=False)
pos_df  = pd.read_csv(f"{DATA_RES}/player_rolling.csv")

matches["match_id"]  = matches["match_id"].astype(str)
players["match_id"]  = players["match_id"].astype(str)
players["team_name"] = players["team_name"].str.replace(r"\s*W$","",regex=True).str.strip()
matches["home_team"] = matches["home_team"].str.replace(r"\s*W$","",regex=True).str.strip()
matches["away_team"] = matches["away_team"].str.replace(r"\s*W$","",regex=True).str.strip()
matches = matches.drop_duplicates(subset=["match_id"], keep="first").reset_index(drop=True)
players = players.drop_duplicates(subset=["match_id","player_name"], keep="first").reset_index(drop=True)

pos_map = dict(zip(pos_df["player_name"], pos_df["position"]))

def parse_date(s):
    s = str(s)
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d",
                "samedi %d %B %Y - %H:%M", "Saturday %d %B %Y - %H:%M",
                "dimanche %d %B %Y - %H:%M", "Sunday %d %B %Y - %H:%M",
                "lundi %d %B %Y - %H:%M", "Monday %d %B %Y - %H:%M"]:
        try: return pd.to_datetime(s, format=fmt)
        except: pass
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

matches["match_dt"] = matches["match_datetime"].apply(parse_date)

def safe_float(v):
    try: f=float(v); return 0.0 if f!=f else f
    except: return 0.0

players["pis_match"] = players.apply(lambda r: min(
    safe_float(r.get("att_pts",0))*1.0 +
    safe_float(r.get("blocks",0))*1.3 +
    safe_float(r.get("srv_ace",0))*1.2 +
    (safe_float(r.get("srv_err",0))+safe_float(r.get("att_err",0)))*(-0.8), 30.0), axis=1)
players["position"] = players["player_name"].map(pos_map).fillna("OH")
is_lib = players["libero"].astype(str).str.lower().isin(["1","true","1.0","yes"])
players.loc[is_lib, "position"] = "L"
players = players.merge(matches[["match_id","match_dt"]], on="match_id", how="left")

print(f"Zawodniczek: {len(players)}, Meczów: {matches['match_id'].nunique()}")

has_odds = matches["closing_home_odds"].notna() & matches["closing_away_odds"].notna()
wf_matches = matches[has_odds].sort_values("match_dt").reset_index(drop=True)
print(f"Meczów do WF: {len(wf_matches)}\n")

def rolling_pis_wf(pis_vals):
    n=len(pis_vals)
    if n==0: return 0.0
    s=pis_vals.mean()
    l5=pis_vals[-5:].mean() if n>=5 else s
    l3=pis_vals[-3:].mean() if n>=3 else s
    return l3*roll_w["weight_last_3"]+l5*roll_w["weight_last_5"]+s*roll_w["weight_season"]

def team_tis_wf(past_p, team):
    tr=past_p[past_p["team_name"]==team]
    if tr.empty: return 0.0
    rolling=(tr.sort_values("match_dt")
               .groupby(["player_name","position"])["pis_match"]
               .apply(lambda x: rolling_pis_wf(x.values))
               .reset_index().rename(columns={"pis_match":"pis_rolling"}))
    slots={"S":1,"OPP":1,"OH":2,"MB":2,"L":1}
    tis,used=0.0,set()
    for pos,count in slots.items():
        cands=rolling[rolling["position"]==pos].sort_values("pis_rolling",ascending=False)
        taken=0
        for _,r in cands.iterrows():
            if taken>=count: break
            if r["player_name"] in used: continue
            tis+=r["pis_rolling"]*role_w.get(pos,1.0)
            used.add(r["player_name"]); taken+=1
    return tis

def team_form_wf(past_m, team):
    hm=past_m[past_m["home_team"]==team].copy()
    hm["won"]=(hm["home_sets"]>hm["away_sets"]).astype(float)
    am=past_m[past_m["away_team"]==team].copy()
    am["won"]=(am["away_sets"]>am["home_sets"]).astype(float)
    all_m=pd.concat([hm[["match_dt","won"]],am[["match_dt","won"]]]).sort_values("match_dt")
    if len(all_m)==0: return 0.5,0.5,0.0
    wr=all_m["won"].mean()
    l5=all_m.tail(5)["won"].mean() if len(all_m)>=5 else wr
    return wr,l5,l5-wr

results=[]
for i,match in wf_matches.iterrows():
    mid=match["match_id"]; mdt=match["match_dt"]
    home=match["home_team"]; away=match["away_team"]
    h_odds=float(match["closing_home_odds"]); a_odds=float(match["closing_away_odds"])
    past_p=players[players["match_dt"]<mdt]
    past_m=matches[matches["match_dt"]<mdt]
    tis_h=team_tis_wf(past_p,home); tis_a=team_tis_wf(past_p,away)
    wr_h,l5_h,tr_h=team_form_wf(past_m,home)
    wr_a,l5_a,tr_a=team_form_wf(past_m,away)
    margin=1/h_odds+1/a_odds; wp_mkt=(1/h_odds)/margin
    tis_tot=tis_h+tis_a
    tis_sig=((tis_h/tis_tot-0.5)*tis_w) if tis_tot>0 else 0
    form_sig=((l5_h-l5_a)*0.6+(tr_h-tr_a)*0.4)*form_w
    adj=float(np.clip(tis_sig+form_sig,-max_adj,max_adj))
    wp_final=float(np.clip(wp_mkt+adj,0.01,0.99))
    edge_h=round(wp_final-wp_mkt,5)
    sets_h=match.get("home_sets",np.nan); sets_a=match.get("away_sets",np.nan)
    winner="HOME" if float(sets_h or 0)>float(sets_a or 0) else "AWAY"
    def dec(e):
        ae=abs(e)
        if ae>=0.07: return "STRONG_BET" if e>0 else "STRONG_LAY"
        if ae>=0.05: return "VALUE_BET" if e>0 else "VALUE_LAY"
        if ae>=0.02: return "WATCH"
        return "NO_BET"
    results.append({"match_id":mid,"match_date":mdt,"home":home,"away":away,
        "tis_h":round(tis_h,3),"tis_a":round(tis_a,3),
        "wp_market_h":round(wp_mkt,5),"wp_final_h":round(wp_final,5),
        "adj":round(adj,5),"adj_tis":round(tis_sig,5),"adj_form":round(form_sig,5),
        "edge_h":edge_h,"dec_h":dec(edge_h),"odds_h":h_odds,"odds_a":a_odds,
        "sets_h":sets_h,"sets_a":sets_a,"winner":winner})
    if (i+1)%30==0: print(f"  [{i+1}/{len(wf_matches)}] done")

wf_df=pd.DataFrame(results)
wf_df.to_csv(f"{DATA_RES}/predictions_wf.csv",index=False)
print(f"→ predictions_wf.csv zapisany ({len(wf_df)} meczów)")

def log_loss(y,p):
    p=np.clip(p,1e-7,1-1e-7)
    return -np.mean(y*np.log(p)+(1-y)*np.log(1-p))
def brier(y,p): return np.mean((p-y)**2)

wf_df["home_win"]=(wf_df["winner"]=="HOME").astype(int)
actual=wf_df["home_win"]
ll_mkt=log_loss(actual,wf_df["wp_market_h"])
ll_wf=log_loss(actual,wf_df["wp_final_h"])
bs_mkt=brier(actual,wf_df["wp_market_h"])
bs_wf=brier(actual,wf_df["wp_final_h"])

pred_v31=pd.read_csv(f"{DATA_RES}/predictions_v3.csv")
pred_v31=pred_v31[pred_v31["odds_h"].notna()].copy()
pred_v31["home_win"]=(pred_v31["winner"]=="HOME").astype(int)
ll_v31=log_loss(pred_v31["home_win"],pred_v31["wp_final_h"])

print("\n"+"="*62)
print("WALK-FORWARD vs v3.1 (leaky) vs RYNEK")
print("="*62)
print(f"Meczów: {len(wf_df)}")
print(f"\n{'Metryka':<20} {'Rynek':>8} {'v3.1 leaky':>12} {'WF czysty':>11} {'Δ(WF-rynek)':>12}")
print("-"*65)
print(f"{'Log Loss':<20} {ll_mkt:>8.4f} {ll_v31:>12.4f} {ll_wf:>11.4f} {ll_wf-ll_mkt:>+12.4f}")
print(f"{'Brier Score':<20} {bs_mkt:>8.4f} {'—':>12} {bs_wf:>11.4f} {bs_wf-bs_mkt:>+12.4f}")

print("\n--- ROI walk-forward ---")
for label,thr in [("VALUE (>5pp)",0.05),("WATCH (>2pp)",0.02),("SMALL (>1pp)",0.01)]:
    sub=wf_df[abs(wf_df["edge_h"])>=thr]
    if len(sub)==0: continue
    pnl,wins,bets=0,0,0
    for _,r in sub.iterrows():
        mp=r["wp_market_h"]
        if mp<=0 or mp>=1: continue
        if r["edge_h"]>0: odds=1/mp; won=r["home_win"]==1
        else: odds=1/(1-mp); won=r["home_win"]==0
        pnl+=(odds-1) if won else -1
        wins+=int(won); bets+=1
    if bets>0:
        print(f"  {label}: {bets} zakł, {wins} wins, P&L={pnl:+.2f}u, ROI={pnl/bets*100:+.1f}%")

print("\n--- Chronologiczny split ---")
wf_s=wf_df.sort_values("match_date").reset_index(drop=True)
n2=len(wf_s)//2
for half,lbl in [(wf_s.iloc[:n2],f"Pierwsze {n2}"),(wf_s.iloc[n2:],f"Drugie {len(wf_s)-n2}")]:
    lm=log_loss(half["home_win"],half["wp_market_h"])
    lmod=log_loss(half["home_win"],half["wp_final_h"])
    sub=half[abs(half["edge_h"])>=0.01]
    pnl,bets=0,0
    for _,r in sub.iterrows():
        mp=r["wp_market_h"]
        if mp<=0 or mp>=1: continue
        if r["edge_h"]>0: odds=1/mp; won=r["home_win"]==1
        else: odds=1/(1-mp); won=r["home_win"]==0
        pnl+=(odds-1) if won else -1; bets+=1
    roi=pnl/bets*100 if bets>0 else 0
    print(f"\n{lbl} meczów: LL rynek={lm:.4f} WF={lmod:.4f} delta={lmod-lm:+.4f} | ROI={roi:+.1f}% ({bets} zakł)")

gap=ll_wf-ll_mkt
print("\n"+"="*62)
if gap<-0.005: print(f"WERDYKT: PRAWDZIWY EDGE — {ll_mkt:.4f} → {ll_wf:.4f} ({gap:+.4f})")
elif gap<0: print(f"WERDYKT: MARGINALNY EDGE ({gap:+.4f})")
else: print(f"WERDYKT: BRAK EDGE BEZ LEAKAGE ({gap:+.4f})")
print("="*62)
