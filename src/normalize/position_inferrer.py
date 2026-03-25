
from collections import defaultdict, Counter

def infer_position(avg_att, avg_blk, avg_rec, avg_pts, matches, libero_flag):
    if libero_flag == "L": return "L", "HIGH", "libero_flag"
    if avg_att == 0 and avg_blk == 0 and avg_rec > 5: return "L", "MEDIUM", "att=0 blk=0 rec>5"
    if avg_blk >= 1.0 and avg_rec <= 2.0 and avg_att <= 5.0: return "MB", "MEDIUM", f"blk={avg_blk:.1f}"
    if avg_att >= 6.0 and avg_rec <= 3.0: return "OPP", "MEDIUM", f"att={avg_att:.1f}"
    if avg_att >= 3.0 and avg_rec >= 3.0: return "OH", "MEDIUM", f"att={avg_att:.1f} rec={avg_rec:.1f}"
    if avg_pts <= 3.0 and avg_blk < 1.0 and avg_att < 3.0 and matches >= 5: return "S", "LOW", "low_all"
    if avg_blk >= 0.8 and avg_att < 5.0: return "MB", "LOW", f"blk={avg_blk:.1f}"
    if avg_att >= 1.0 or avg_pts >= 2.0: return "OH", "LOW", "active"
    return "UNKNOWN", "NO_DATA", "insufficient"

def _sf(v):
    if v is None: return 0.0
    try:
        if isinstance(v, str):
            v = v.strip().replace(",",".")
            if v in ("","none","null","-"): return 0.0
        return float(v)
    except: return 0.0

def build_position_table(clean_players):
    agg = defaultdict(lambda:{"att":0,"blk":0,"ace":0,"se":0,"ae":0,"rec":0,"pts":0,"n":0,"team":"","lib":""})
    for p in clean_players:
        name = p.get("player_name","").strip()
        if not name: continue
        a = agg[name]
        a["att"]+=_sf(p.get("att_pts",0)); a["blk"]+=_sf(p.get("blocks",0))
        a["ace"]+=_sf(p.get("srv_ace",0)); a["se"]+=_sf(p.get("srv_err",0))
        a["ae"]+=_sf(p.get("att_err",0));  a["rec"]+=_sf(p.get("rec_tot",0))
        a["pts"]+=_sf(p.get("total_pts",0)); a["n"]+=1
        a["team"]=p.get("team_name","")
        if str(p.get("libero","")).strip().upper()=="L": a["lib"]="L"
    results = []
    for name,a in agg.items():
        n=max(a["n"],1)
        pos,conf,reason=infer_position(
            round(a["att"]/n,2),round(a["blk"]/n,2),
            round(a["rec"]/n,2),round(a["pts"]/n,2),a["n"],a["lib"])
        results.append({"player_name":name,"team_name":a["team"],
            "position_inferred":pos,"pos_confidence":conf,
            "matches_played":a["n"],"avg_att_pts":round(a["att"]/n,2),
            "avg_blocks":round(a["blk"]/n,2),"avg_rec_tot":round(a["rec"]/n,2)})
    return results
