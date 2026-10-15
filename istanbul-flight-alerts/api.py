"""REST API. A separate Python host is needed for 24/7 HTTP availability."""
import os
import secrets
from fastapi import FastAPI, Header, HTTPException
from flight_alerts import DESTINATIONS, MFA_URL, load_state, scan
app=FastAPI(title="Istanbul Visa-Free Flight Alert API",version="1.0.0")

@app.get("/health")
def health():
 s=load_state()
 return {"status":"ok","last_run":s["last_run"],"checked":s["checked"],"cached_not_live":True}

@app.get("/destinations")
def destinations():
 return {"passport":"TR ordinary/bordo","visa_reference":MFA_URL,
         "airports":[{"code":k,"city":v[0],"country":v[1]} for k,v in DESTINATIONS.items()]}

@app.get("/deals")
def deals():
 s=load_state()
 return {"cached_not_live":True,"last_run":s["last_run"],"deals":s["latest_deals"]}

@app.post("/scan")
def manual_scan(x_api_key:str|None=Header(default=None)):
 secret=os.getenv("ADMIN_API_KEY")
 if not secret or not x_api_key or not secrets.compare_digest(secret,x_api_key):
  raise HTTPException(status_code=401,detail="Invalid API key")
 try:
  found=scan()
 except Exception as exc:
  raise HTTPException(status_code=502,detail="Flight provider/SMTP scan failed") from exc
 return {"alerts":len(found),"cached_not_live":True}
