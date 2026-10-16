from core.formula_engine import solve

def solve_a(q):
    tid=q.get("generation_metadata",{}).get("template_used",""); v=q.get("variables") or q.get("generation_metadata",{}).get("variables_used",{})
    try:
        ans,unit,derivation=solve(tid,v)
        text=str(ans) if unit=="ratio" else f"{ans} {unit}"
        return {"equation_model":tid,"derivation":derivation,"answer":text,"answer_value":ans,"unit":unit,"confidence":1.0}
    except Exception as e: return {"equation_model":tid,"derivation":str(e),"answer":"","confidence":0.0}
