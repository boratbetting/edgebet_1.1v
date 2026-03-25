
def calculate_start_rate(match_history, team_matches, boost_weights):
    if not match_history: return {"start_rate":0,"recent_start_rate":0,"matches_played":0}
    n=len(match_history)
    sr=sum(1 for m in match_history if m.get("starter_flag",0))/n
    recent=match_history[-len(boost_weights):]
    w=boost_weights[:len(recent)]
    ws=sum(r.get("starter_flag",0)*wt for r,wt in zip(recent,w))
    wt=sum(w)
    rsr=ws/wt if wt>0 else sr
    return {"start_rate":round(sr,4),"recent_start_rate":round(rsr,4),"matches_played":n}
