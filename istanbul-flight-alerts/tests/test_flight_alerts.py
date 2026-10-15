import unittest
from datetime import date, datetime, timedelta, timezone
from flight_alerts import DESTINATIONS, blank, config, evaluate, months, normalize

class ScannerTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,15,12,tzinfo=timezone.utc)
  self.cfg=config()
  self.sample={"origin_airport":"SAW","destination_airport":"BEG","price":4500,
    "departure_at":"2026-12-02","return_at":"2026-12-06",
    "transfers":0,"return_transfers":0,"link":"/book/"}
 def test_nineteen_destinations(self):
  self.assertEqual(len(DESTINATIONS),19)
 def test_legitimate_roundtrip(self):
  self.assertEqual(normalize(self.sample,self.cfg,self.now.date())["price"],4500)
 def test_transit_not_allowed(self):
  self.assertIsNone(normalize({**self.sample,"transfers":1},self.cfg,self.now.date()))
 def test_schengen_not_allowed(self):
  self.assertIsNone(normalize({**self.sample,"destination_airport":"FCO"},self.cfg,self.now.date()))
 def test_oneway_not_allowed(self):
  sample={k:v for k,v in self.sample.items() if k!="return_at"}
  self.assertIsNone(normalize(sample,self.cfg,self.now.date()))
 def test_first_run_absolute_deal(self):
  self.assertEqual(len(evaluate([self.sample],blank(),self.cfg,self.now)),1)
 def test_duplicate_alert_not_sent(self):
  state=blank()
  deal=evaluate([self.sample],state,self.cfg,self.now)[0]
  state["alerts"][deal["key"]]={"price":4500,"sent_at":self.now.isoformat()}
  self.assertEqual(evaluate([self.sample],state,self.cfg,self.now),[])
 def test_three_day_baseline(self):
  state=blank()
  high={**self.sample,"price":7000}
  key=normalize(high,self.cfg,self.now.date())["key"]
  state["history"][key]={"prices":[{"day":(self.now.date()-timedelta(days=i)).isoformat(),"price":7500} for i in (3,2,1)],
                         "last_seen":self.now.date().isoformat()}
  self.assertEqual(len(evaluate([{**high,"price":4500}],state,self.cfg,self.now)),1)
 def test_month_boundary(self):
  self.assertEqual(months(date(2026,12,15),date(2027,2,3)),["2026-12","2027-01","2027-02"])

if __name__=="__main__": unittest.main()
