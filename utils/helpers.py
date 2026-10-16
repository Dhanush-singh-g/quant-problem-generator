import json,re
from services.ai_gateway import gateway

def llm_call(messages,model="gemini-2.5-flash",temperature=0.0,max_tokens=800):
    prompt="\n".join(f"{m.get('role','user').upper()}: {m.get('content','')}" for m in messages)
    text,meta=gateway.generate(prompt,model=model)
    if text is None: raise RuntimeError(meta.get("reason","AI unavailable"))
    return text

def safe_parse_json(text):
    if text is None:return {"error":"no_text","raw":""}
    cleaned=text.replace("```json","").replace("```","").strip()
    try:return json.loads(cleaned)
    except Exception: pass
    # object extraction supporting nested JSON
    start=cleaned.find("{")
    if start<0:return {"error":"invalid_json","raw":cleaned}
    depth=0; in_str=False; esc=False
    for i,ch in enumerate(cleaned[start:],start):
        if in_str:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch=='"': in_str=False
        else:
            if ch=='"': in_str=True
            elif ch=='{': depth+=1
            elif ch=='}':
                depth-=1
                if depth==0:
                    try:return json.loads(cleaned[start:i+1])
                    except Exception:break
    return {"error":"invalid_json","raw":cleaned}
