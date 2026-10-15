"""Istanbul Flight Alert scanner, standard-library only; fare data is cached."""
import argparse
import html
import json
import os
import smtplib
import ssl
import statistics
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

ORIGINS = ("IST", "SAW")
DESTINATIONS = {
 "TIA":("Tiran","Arnavutluk"),"BEG":("Belgrad","Sırbistan"),
 "SJJ":("Saraybosna","Bosna-Hersek"),"PRN":("Priştine","Kosova"),
 "SKP":("Üsküp","Kuzey Makedonya"),"TGD":("Podgorica","Karadağ"),
 "TIV":("Tivat","Karadağ"),"TBS":("Tiflis","Gürcistan"),
 "BUS":("Batum","Gürcistan"),"KUT":("Kutaisi","Gürcistan"),
 "GYD":("Bakü","Azerbaycan"),"CMN":("Kazablanka","Fas"),
 "RAK":("Marakeş","Fas"),"TUN":("Tunus","Tunus"),
 "DOH":("Doha","Katar"),"AMM":("Amman","Ürdün"),
 "TAS":("Taşkent","Özbekistan"),"ALA":("Almatı","Kazakistan"),
 "ECN":("Ercan","KKTC")}
MFA_URL = "https://www.mfa.gov.tr/turk-vatandaslarinin-tabi-oldugu-vize-uygulamalari.tr.mfa"
API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
STATE_PATH = Path(__file__).resolve().parent / "data" / "state.json"

def config():
 return {
  "absolute":int(os.getenv("ABSOLUTE_PRICE_TRY","5000")),
  "drop":float(os.getenv("DROP_PERCENT","30")),
  "saving":int(os.getenv("MIN_SAVING_TRY","1800")),
  "advance_min":int(os.getenv("MIN_ADVANCE_DAYS","21")),
  "advance_max":int(os.getenv("MAX_ADVANCE_DAYS","180")),
  "nights_min":int(os.getenv("MIN_NIGHTS","2")),
  "nights_max":int(os.getenv("MAX_NIGHTS","10")),
  "max_email":int(os.getenv("MAX_ALERTS_EMAIL","12"))}

def blank():
 return {"version":1,"history":{},"alerts":{},"latest_deals":[],"last_run":None,"checked":0}

def load_state(path=STATE_PATH):
 if not path.exists(): return blank()
 state=json.loads(path.read_text(encoding="utf-8"))
 if state.get("version")!=1: raise ValueError("Incompatible state version")
 return state

def save_state(state,path=STATE_PATH):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp")
 tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 tmp.replace(path)

def months(a,b):
 result=[]
 y,m=a.year,a.month
 while (y,m)<=(b.year,b.month):
  result.append(f"{y:04d}-{m:02d}")
  y,m=(y+1,1) if m==12 else (y,m+1)
 return result

def fetch_offers(token,cfg,today):
 if not token: raise ValueError("TRAVELPAYOUTS_TOKEN is required")
 all_offers=[]
 period=months(today+timedelta(days=cfg["advance_min"]),today+timedelta(days=cfg["advance_max"]))
 for origin in ORIGINS:
  for month in period:
   for page in (1,2):
    query=urllib.parse.urlencode({"origin":origin,"departure_at":month,"one_way":"false",
      "direct":"true","unique":"false","sorting":"price","currency":"try","limit":1000,"page":page})
    req=urllib.request.Request(API_URL+"?"+query,headers={
      "X-Access-Token":token,"Accept":"application/json","User-Agent":"istanbul-flight-alerts/1.0"})
    with urllib.request.urlopen(req,timeout=25) as response: payload=json.load(response)
    if payload.get("success") is not True or not isinstance(payload.get("data"),list):
     raise RuntimeError(f"Invalid flight API response: {origin} {month} {page}")
    if payload.get("currency") and str(payload["currency"]).upper()!="TRY":
     raise RuntimeError("Currency mismatch; refused to compare prices")
    data=payload["data"]
    all_offers.extend(data)
    if len(data)<1000: break
 return all_offers

def normalize(raw,cfg,today):
 try:
  origin=str(raw.get("origin_airport") or raw.get("origin") or "").upper()
  dest=str(raw.get("destination_airport") or raw.get("destination") or "").upper()
  departure=date.fromisoformat(str(raw["departure_at"])[:10])
  returning=date.fromisoformat(str(raw["return_at"])[:10])
  price=int(float(raw["price"]))
  stops=int(raw.get("transfers",0))
  return_stops=int(raw.get("return_transfers",0))
 except (KeyError,ValueError,TypeError,OverflowError): return None
 if not(origin in ORIGINS and dest in DESTINATIONS and price>0 and stops==0 and return_stops==0
    and cfg["advance_min"]<=(departure-today).days<=cfg["advance_max"]
    and cfg["nights_min"]<=(returning-departure).days<=cfg["nights_max"]): return None
 link=raw.get("link")
 url="https://www.aviasales.com"+link if isinstance(link,str) and link.startswith("/") and not link.startswith("//") else "https://www.aviasales.com/"
 city,country=DESTINATIONS[dest]
 return {"key":f"{origin}|{dest}|{departure}|{returning}|0|0",
         "origin":origin,"destination":dest,"city":city,"country":country,
         "departure":departure.isoformat(),"return":returning.isoformat(),
         "price":price,"currency":"TRY","url":url}

def evaluate(raw,state,cfg,now):
 today=now.date()
 offers={}
 for item in raw:
  offer=normalize(item,cfg,today)
  if offer and (offer["key"] not in offers or offer["price"]<offers[offer["key"]]["price"]):
   offers[offer["key"]]=offer
 deals=[]
 for key,offer in offers.items():
  record=state["history"].setdefault(key,{"prices":[],"last_seen":today.isoformat()})
  previous=record["prices"]
  recent=[p for p in previous if 0<(today-date.fromisoformat(p["day"])).days<=45]
  median=statistics.median(p["price"] for p in recent) if len({p["day"] for p in recent})>=3 else None
  price=offer["price"]
  drop=round(100*(median-price)/median,1) if median else None
  reasons=[]
  if price<=cfg["absolute"]: reasons.append("Düşük fiyat")
  if drop is not None and drop>=cfg["drop"] and median-price>=cfg["saving"]:
   reasons.append("Tarihsel medyana göre indirim")
  alert=state["alerts"].get(key)
  eligible=alert is None
  if alert:
   hours=(now-datetime.fromisoformat(alert["sent_at"])).total_seconds()/3600
   improvement=100*(alert["price"]-price)/alert["price"]
   eligible=price<alert["price"] and (improvement>=10 or hours>=168)
  if reasons and eligible:
   deals.append({**offer,"median_try":int(median) if median else None,
                 "drop_percent":drop,"reasons":reasons})
  if previous and previous[-1]["day"]==today.isoformat():
   previous[-1]["price"]=min(previous[-1]["price"],price)
  else: previous.append({"day":today.isoformat(),"price":price})
  record["prices"]=[p for p in previous if (today-date.fromisoformat(p["day"])).days<=45][-45:]
  record["last_seen"]=today.isoformat()
 keep=sorted(state["history"],key=lambda k:state["history"][k]["last_seen"],reverse=True)[:3000]
 state["history"]={k:state["history"][k] for k in keep}
 state["checked"]=len(offers)
 state["last_run"]=now.isoformat()
 return sorted(deals,key=lambda d:(-(d["drop_percent"] or 0),d["price"]))

def send_email(deals):
 if not deals: return
 host,user,password,to=(os.environ[k] for k in ("SMTP_HOST","SMTP_USER","SMTP_PASSWORD","ALERT_TO"))
 port=int(os.getenv("SMTP_PORT","465"))
 lines=[]
 for d in deals:
  discount=f" (%{d['drop_percent']} indirim)" if d["drop_percent"] else ""
  lines.append("<tr><td>{}</td><td>{}</td><td>{} - {}</td><td>{:,} TRY{}</td><td><a href='{}'>Teklifi kontrol et</a></td></tr>".format(
   html.escape(d["city"]),html.escape(d["origin"]),html.escape(d["departure"]),
   html.escape(d["return"]),d["price"],html.escape(discount),html.escape(d["url"],quote=True)))
 body=("<h2>Vizesiz Uçuş Fırsatları</h2><table border='1'><tr><th>Şehir</th><th>Kalkış</th><th>Tarih</th><th>Fiyat</th><th>Link</th></tr>"
       +"".join(lines)+"</table><p>Önbellek uçuş fiyatıdır; nihai satış fiyatı ve giriş koşullarını kontrol edin.</p>"
       +f"<a href='{MFA_URL}'>Dışişleri vize bilgisi</a>")
 msg=EmailMessage()
 msg["From"],msg["To"],msg["Subject"]=user,to,f"Uçuş fırsatları: {len(deals)} kritik fiyat"
 msg.set_content("Teklifleri HTML görünümünde görebilirsiniz.")
 msg.add_alternative(body,subtype="html")
 context=ssl.create_default_context()
 if port==465:
  with smtplib.SMTP_SSL(host,port,context=context,timeout=25) as smtp:
   smtp.login(user,password)
   smtp.send_message(msg)
 else:
  with smtplib.SMTP(host,port,timeout=25) as smtp:
   smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
   smtp.login(user,password); smtp.send_message(msg)

def scan():
 required=("TRAVELPAYOUTS_TOKEN","SMTP_HOST","SMTP_USER","SMTP_PASSWORD","ALERT_TO")
 missing=[k for k in required if not os.getenv(k)]
 if missing: raise RuntimeError("Missing configuration: "+", ".join(missing))
 state=load_state()
 now=datetime.now(timezone.utc)
 cfg=config()
 deals=evaluate(fetch_offers(os.environ["TRAVELPAYOUTS_TOKEN"],cfg,now.date()),state,cfg,now)
 selected=deals[:cfg["max_email"]]
 if selected:
  send_email(selected)
  for d in selected:
   state["alerts"][d["key"]]={"price":d["price"],"sent_at":now.isoformat(),"deal":d}
 state["latest_deals"]=selected
 save_state(state)
 print(json.dumps({"last_run":state["last_run"],"checked":state["checked"],"offers_emailed":len(selected)}))
 return selected

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("command",choices=("scan","demo","status"))
 args=p.parse_args()
 if args.command=="scan": scan()
 elif args.command=="status":
  state=load_state(); print(json.dumps({"last_run":state["last_run"],"checked":state["checked"]}))
 else:
  today=datetime.now(timezone.utc)
  sample=[{"origin_airport":"SAW","destination_airport":"BEG","price":4200,
    "departure_at":(today+timedelta(days=45)).date().isoformat(),
    "return_at":(today+timedelta(days=49)).date().isoformat(),
    "transfers":0,"return_transfers":0}]
  print(json.dumps(evaluate(sample,blank(),config(),today),ensure_ascii=False,indent=2))
