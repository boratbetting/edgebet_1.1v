
def calculate_pis_rolling(history, params):
    if not history: return {"pis_last_3":0,"pis_last_5":0,"pis_season":0,"pis_rolling":0,"matches_played":0,"data_quality":"NO_DATA"}
    vals=[v for _,v in sorted(history,key=lambda x:x[0])]
    n=len(vals)
    season=sum(vals)/n
    last5=sum(vals[-5:])/min(n,5)
    last3=sum(vals[-3:])/min(n,3)
    w=params
    rolling=last3*w["weight_last_3"]+last5*w["weight_last_5"]+season*w["weight_season"]
    dq="HIGH" if n>=5 else ("MEDIUM" if n>=3 else "LOW")
    return {"pis_last_3":round(last3,4),"pis_last_5":round(last5,4),
            "pis_season":round(season,4),"pis_rolling":round(rolling,4),
            "matches_played":n,"data_quality":dq}
