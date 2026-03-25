
def select_typical_lineup(roster, role_weights):
    slots={"S":1,"OPP":1,"OH":2,"MB":2,"L":1}
    lineup={}; used=set()
    for pos,count in slots.items():
        cands=[r for r in roster if r.get("position")==pos and r["player_name"] not in used]
        cands.sort(key=lambda x:float(x.get("pis_rolling",0)),reverse=True)
        for i in range(count):
            slot=f"{pos}" if count==1 else f"{pos}{i+1}"
            if i<len(cands):
                lineup[slot]={"player_id":cands[i]["player_name"],
                    "player_name":cands[i]["player_name"],
                    "pis_rolling":float(cands[i].get("pis_rolling",0)),
                    "position":pos}
                used.add(cands[i]["player_name"])
            else:
                lineup[slot]={"player_id":None,"player_name":None,"pis_rolling":0,"position":pos}
    return lineup

def calculate_tis(lineup):
    weights={"S":1.25,"OPP":1.20,"OH":1.10,"MB":1.00,"L":0.90}
    tis=0.0
    for slot,p in lineup.items():
        if p.get("player_id"):
            pos=p.get("position","OH")
            tis+=float(p.get("pis_rolling",0))*weights.get(pos,1.0)
    return round(tis,4)

def calculate_lineup_shock(tis_live, tis_typical):
    if tis_typical==0: return 0
    return round((tis_live-tis_typical)/tis_typical,4)
