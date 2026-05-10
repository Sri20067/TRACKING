import urllib.request
import json
import time

URL = "http://127.0.0.1:5000/send_gps"
VEHICLE_ID = "TN09AB1234"

EXC = (12.86945, 80.21583)
DUMP = (12.86990, 80.21583)
OUT = (12.86960, 80.21583)

def send(lat, lon):
    data = {"vehicle_id": VEHICLE_ID, "latitude": lat, "longitude": lon, "timestamp": "2026-05-07T09:40:00"}
    req = urllib.request.Request(URL, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    res = urllib.request.urlopen(req).read().decode('utf-8')
    print(res)
    time.sleep(0.5)

print("Resetting trips via /reset_trips first")
urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:5000/reset_trips", method='POST'))

print("Trip 1")
send(*EXC)
send(*OUT)
send(*DUMP)

print("Trip 2 (exceeding limit of 1)")
send(*EXC)
send(*OUT)
send(*DUMP)

print("Check server logs for SMS attempt!")
