
def calculate_pis_match(att_pts,blocks,srv_ace,srv_err,att_err,params):
    w=params
    pis=(att_pts*w["att_pts_w"]+blocks*w["blocks_w"]+srv_ace*w["srv_ace_w"]
         +(srv_err+att_err)*w["srv_err_w"])
    pis=min(pis,w["sanity_cap"])
    return {"pis_match":round(pis,4)}
