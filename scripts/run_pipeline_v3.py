
import os, sys, csv, json, yaml, math
from datetime import date, datetime
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.normalize.deduplicator import deduplicate_matches, deduplicate_player_stats
from src.features.pis_calculator import calculate_pis_match
from src.features.pis_rolling import calculate_pis_rolling
from src.features.start_rate import calculate_start_rate
from src.lineup.typical_lineup import select_typical_lineup, calculate_tis, calculate_lineup_shock
from src.normalize.position_inferrer import build_position_table

def load_csv(fp):
    with open(fp,"r",encoding="utf-8-sig") as f: return list(csv.DictReader(f))
def save_csv(data,fp):
    if not data: return
    os.makedirs(os.path.dirname(fp) or ".",exist_ok=True)
    with open(fp,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0].keys()),extrasaction="ignore")
        w.writeheader(); w.writerows(data)
def si(v):
    if v is None: return 0
    try:
        if isinstance(v,str):
            v=v.strip().replace(",",".")
            if v in ("","none","null","-"): return 0
        return int(float(v))
    except: return 0
def sf(v):
    if v is None: return None
    try:
        if isinstance(v,str):
            v=v.strip().replace(",",".")
            if v in ("","none","null","-"): return None
        r=float(v); return r if r>0 else None
    except: return None
def pd(s):
    if not s: return date(2025,1,1)
    s=str(s).strip()
    for fmt in ["%Y-%m-%dT%H:%M:%S","%Y-%m-%d","%B %d, %Y","%d/%m/%Y","%m/%d/%Y"]:
        try: return datetime.strptime(s.split("T")[0] if "T" in s else s,fmt.split("T")[0]).date()
        except: continue
    return date(2025,1,1)

def calculate_team_form(matches,team_name,as_of_date=None):
    team_matches=[]
    for m in matches:
        h=m.get("home_team","").strip(); a=m.get("away_team","").strip()
        if h!=team_name and a!=team_name: continue
        md=pd(m.get("match_datetime",""))
        if as_of_date and md>=as_of_date: continue
        hs=si(m.get("home_sets",0)); aws=si(m.get("away_sets",0))
        if hs==0 and aws==0: continue
        is_home=(h==team_name)
        won=(is_home and hs>aws) or (not is_home and aws>hs)
        sw=hs if is_home else aws; sl=aws if is_home else hs
        team_matches.append({"date":md,"won":won,"is_home":is_home,
            "set_ratio":sw/max(sw+sl,1)})
    team_matches.sort(key=lambda x:x["date"])
    n=len(team_matches)
    if n==0: return {"win_rate":0.5,"win_rate_last5":0.5,"set_ratio":0.5,"form_trend":0.0,"matches_played":0}
    wr=sum(1 for m in team_matches if m["won"])/n
    last5=team_matches[-5:] if n>=5 else team_matches
    wr5=sum(1 for m in last5 if m["won"])/len(last5)
    sr=sum(m["set_ratio"] for m in team_matches)/n
    return {"win_rate":round(wr,4),"win_rate_last5":round(wr5,4),
            "set_ratio":round(sr,4),"form_trend":round(wr5-wr,4),"matches_played":n}

def calculate_depth_risk(lineup):
    empty=sum(1 for v in lineup.values() if v.get("player_id") is None)
    low=sum(1 for v in lineup.values() if v.get("player_id") is not None and float(v.get("pis_rolling",0))<2.0)
    return {"empty_slots":empty,"low_pis_slots":low,"depth_risk":round(empty*0.03+low*0.01,4)}

def calculate_adjustment(tis_h,tis_a,form_h,form_a,depth_h,depth_a,config):
    adj_cfg=config.get("adjustment",{})
    tis_w=adj_cfg.get("tis_weight",0.02)
    form_w=adj_cfg.get("form_weight",0.10)
    max_adj=adj_cfg.get("max_adjustment",0.08)
    tis_total=tis_h+tis_a if (tis_h+tis_a)>0 else 1
    tis_sig=(tis_h/tis_total-0.5)*tis_w
    wr5_h=form_h.get("win_rate_last5",0.5); wr5_a=form_a.get("win_rate_last5",0.5)
    tr_h=form_h.get("form_trend",0); tr_a=form_a.get("form_trend",0)
    form_sig=((wr5_h-wr5_a)*form_w*0.6+(tr_h-tr_a)*form_w*0.4)
    raw=tis_sig+form_sig
    adj=max(-max_adj,min(max_adj,raw))
    return {"adjustment":round(adj,6),"tis_signal":round(tis_sig,6),
            "form_signal":round(form_sig,6),"depth_signal":0.0}

def run(raw_dir="data/raw",out_dir="data/results",cfg_path="configs/params_v1.yaml"):
    print("="*60)
    print("BETEDGE PIPELINE v3.0 — RESIDUAL MODEL")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60)
    with open(cfg_path) as f: config=yaml.safe_load(f)
    if "adjustment" not in config:
        config["adjustment"]={"tis_weight":0.02,"form_weight":0.10,"depth_weight":0.0,"max_adjustment":0.08}
    config["model_version"]="v3.1.0"
    print(f"\n[0] Config: {config['model_version']} — RESIDUAL MODEL")

    print("\n[1] Loading + dedup...")
    raw_m=load_csv(os.path.join(raw_dir,"matches.csv"))
    raw_p=load_csv(os.path.join(raw_dir,"players_raw.csv"))
    raw_m_clean=[dict(m,home_team=m.get("home_team","").replace(" W","").strip(),
                        away_team=m.get("away_team","").replace(" W","").strip()) for m in raw_m]
    raw_p_clean=[dict(p,team_name=p.get("team_name","").replace(" W","").strip()) for p in raw_p]
    cm,_,mr=deduplicate_matches(raw_m_clean)
    cp,_,pr=deduplicate_player_stats(raw_p_clean)
    print(f"    M:{mr['input_count']}->{mr['output_count']} P:{pr['input_count']}->{pr['output_count']}")

    print("\n[2] Positions...")
    league_code=config.get("league","FR_LAF_W")
    pos_table=build_position_table(cp, league=league_code)
    pmap={p["player_name"]:p["position_inferred"] for p in pos_table}
    overrides_path=os.path.join(os.path.dirname(cfg_path),"position_overrides.yaml")
    overrides={}
    if os.path.exists(overrides_path):
        with open(overrides_path) as f2: ov_all=yaml.safe_load(f2)
        league=config.get("league","FR_LAF_W")
        overrides=ov_all.get(league,{}) or {}
        if overrides: print(f"    Overrides: {len(overrides)} zawodniczek ({league})")
    for name,pos in overrides.items(): pmap[name]=pos
    for p in cp:
        nm=p.get("player_name","").strip()
        if str(p.get("libero","")).strip().upper()=="L": p["position"]="L"
        elif nm in pmap: p["position"]=pmap[nm]
        else: p["position"]="UNKNOWN"
    for pt in pos_table:
        if pt["player_name"] in overrides: pt["position_inferred"]=overrides[pt["player_name"]]
    pc=Counter(p["position_inferred"] for p in pos_table)
    print(f"    {dict(pc)}")

    print("\n[3] PIS...")
    pp=config["pis"]
    pf={"att_pts_w":pp["att_pts_w"],"blocks_w":pp["blocks_w"],"srv_ace_w":pp["srv_ace_w"],
        "srv_err_w":pp["srv_err_w"],"att_err_w":pp["att_err_w"],"sanity_cap":pp["sanity_cap"]}
    for p in cp:
        r=calculate_pis_match(si(p.get("att_pts",0)),si(p.get("blocks",0)),si(p.get("srv_ace",0)),
            si(p.get("srv_err",0)),si(p.get("att_err",0)),pf)
        p["pis_match"]=r["pis_match"]

    print("\n[4] Rolling + start rate...")
    ph=defaultdict(list)
    for p in cp:
        nm=p.get("player_name","").strip()
        ph[nm].append((pd(p.get("match_datetime","")),float(p.get("pis_match",0))))
    rp=config["rolling"]; rolling=[]
    for nm,h in ph.items():
        h.sort(key=lambda x:x[0])
        r=calculate_pis_rolling(h,params=rp)
        es=[p for p in cp if p.get("player_name","").strip()==nm]
        es.sort(key=lambda p:p.get("match_datetime",""))
        tm=es[-1].get("team_name","") if es else ""
        rolling.append({"player_name":nm,"player_id":nm,"team_name":tm,
            "position":pmap.get(nm,"UNKNOWN"),**r})
    tmc=Counter()
    for m in cm: tmc[m.get("home_team","")]+=1; tmc[m.get("away_team","")]+=1
    for r in rolling:
        nm=r["player_name"]; tm=r["team_name"]; tn=tmc.get(tm,1)
        mh=[{"starter_flag":1 if (si(p.get("set1",0))>0 or str(p.get("libero","")).strip().upper()=="L") else 0}
            for p in cp if p.get("player_name","").strip()==nm]
        sr=calculate_start_rate(mh,tn,config["start_rate"]["recent_boost_weights"])
        r.update(sr)
    save_csv(rolling,os.path.join(out_dir,"player_rolling.csv"))
    save_csv(rolling,os.path.join(out_dir,"player_rolling_v3.csv"))

    print("\n[5] Lineups + TIS...")
    teams=set()
    for m in cm: teams.add(m.get("home_team","").strip()); teams.add(m.get("away_team","").strip())
    teams.discard("")
    rw=config["role_weights"]; all_lin={}; all_tis={}
    for t in sorted(teams):
        roster=[r for r in rolling if r["team_name"].strip()==t.strip()]
        lin=select_typical_lineup(roster,rw); tis=calculate_tis(lin)
        all_lin[t]=lin; all_tis[t]=tis
        filled=sum(1 for v in lin.values() if v["player_id"] is not None)
        print(f"    {t}: TIS={tis:.1f} ({filled}/7)")

    print("\n[6] Team form...")
    all_form={}
    for t in teams:
        form=calculate_team_form(cm,t); all_form[t]=form
        print(f"    {t}: W={form['win_rate']:.0%} L5={form['win_rate_last5']:.0%} trend={form['form_trend']:+.2f}")

    print("\n[7] Depth risk...")
    all_depth={t:calculate_depth_risk(all_lin.get(t,{})) for t in teams}

    print("\n[8] Predictions v3 (residual)...")
    my=[m for m in cm if str(m.get("players_imported","")).strip().upper()=="YES"]
    preds=[]
    for m in my:
        home=m.get("home_team","").strip(); away=m.get("away_team","").strip()
        mid=m.get("match_id","")
        odds_h=sf(m.get("closing_home_odds")); odds_a=sf(m.get("closing_away_odds"))
        tis_h=all_tis.get(home,0); tis_a=all_tis.get(away,0)
        form_h=all_form.get(home,{"win_rate_last5":0.5,"form_trend":0})
        form_a=all_form.get(away,{"win_rate_last5":0.5,"form_trend":0})
        depth_h=all_depth.get(home,{"depth_risk":0})
        depth_a=all_depth.get(away,{"depth_risk":0})
        if odds_h and odds_a and odds_h>1 and odds_a>1:
            raw_h=1/odds_h; raw_a=1/odds_a; total=raw_h+raw_a
            wp_mkt=raw_h/total; wp_mkt_a=raw_a/total
        else:
            wp_mkt=0.5; wp_mkt_a=0.5
        adj=calculate_adjustment(tis_h,tis_a,form_h,form_a,depth_h,depth_a,config)
        wp_final=max(0.01,min(0.99,wp_mkt+adj["adjustment"]))
        edge_h=round(wp_final-wp_mkt,4); edge_a=-edge_h
        ev_h=(wp_final*odds_h-1) if odds_h else None
        ev_a=((1-wp_final)*odds_a-1) if odds_a else None
        def decide(e):
            if e>=0.07: return "STRONG_BET"
            if e>=0.05: return "VALUE_BET"
            if e>=0.02: return "WATCH"
            return "NO_BET"
        actual="HOME" if si(m.get("home_sets",0))>si(m.get("away_sets",0)) else "AWAY"
        preds.append({"match_id":mid,"match_date":m.get("match_datetime",""),
            "home":home,"away":away,"tis_h":tis_h,"tis_a":tis_a,
            "wp_market_h":round(wp_mkt,4),"wp_final_h":round(wp_final,4),
            "adj":adj["adjustment"],"adj_tis":adj["tis_signal"],
            "adj_form":adj["form_signal"],"adj_depth":0,
            "edge_h":edge_h,"edge_a":edge_a,
            "dec_h":decide(edge_h),"dec_a":decide(edge_a),
            "odds_h":odds_h or "","odds_a":odds_a or "",
            "ev_h":round(ev_h,4) if ev_h else "","ev_a":round(ev_a,4) if ev_a else "",
            "sets_h":m.get("home_sets",""),"sets_a":m.get("away_sets",""),"winner":actual})
    save_csv(preds,os.path.join(out_dir,"predictions_v3.csv"))
    with_odds=[p for p in preds if p.get("odds_h") and p["odds_h"]!=""]
    print(f"\n    Predictions: {len(preds)} total, {len(with_odds)} with odds")
    dc=Counter()
    for p in with_odds: dc[p["dec_h"]]+=1; dc[p["dec_a"]]+=1
    print(f"    Decisions: {dict(dc)}")
    print("\n"+"="*60+"  PIPELINE DONE  "+"="*60)

if __name__=="__main__":
    run()
