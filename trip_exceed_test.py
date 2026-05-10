"""
Fast Trip Exceed Simulator 
Simulates 2 trips to test the max_trips limit and trigger Telegram alerts.
Dynamically fetches active zones from the server.
"""

import urllib.request
import urllib.error
import json
import time
from datetime import datetime
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SERVER_URL = "https://127.0.0.1:5000"
VEHICLE_ID = "TN09AB1234"

def get_active_zones():
    req = urllib.request.Request(f"{SERVER_URL}/get_zones", method="GET")
    with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))

def send_gps(lat, lon):
    data = {
        "vehicle_id": VEHICLE_ID,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "timestamp": datetime.now().isoformat()
    }
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVER_URL}/send_gps",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        status = result.get("status", "?")
        trips = result.get("trip_count", "?")
        print(f"  -> ({data['latitude']}, {data['longitude']}) -> {status} | Trips: {trips}")
        return result
    except Exception as e:
        print(f"  Error: {e}")
        return {}

def simulate_one_trip(trip_num, start_pt, mid_pts, end_pt):
    print(f"\nTrip #{trip_num} starting...")

    print("  [Excavation Zone]")
    send_gps(*start_pt)
    time.sleep(1)

    print("  [En Route...]")
    for pt in mid_pts:
        send_gps(*pt)
        time.sleep(1)

    print("  [Dump Zone - Trip Complete!]")
    result = send_gps(*end_pt)
    time.sleep(1)

    print("  [Returning to Excavation...]")
    for pt in reversed(mid_pts):
        send_gps(*pt)
        time.sleep(1)

    send_gps(*start_pt)
    time.sleep(1)

    print(f"Trip #{trip_num} done! Trips counted: {result.get('trip_count', '?')}")
    return result

def main():
    print("=" * 55)
    print("TRIP EXCEED SIMULATOR")
    print("=" * 55)
    
    zones = get_active_zones()
    exc = zones['excavation']
    dmp = zones['dump']
    
    start_pt = ((exc['lat_min']+exc['lat_max'])/2, (exc['lon_min']+exc['lon_max'])/2)
    end_pt = ((dmp['lat_min']+dmp['lat_max'])/2, (dmp['lon_min']+dmp['lon_max'])/2)
    
    # 2 points exactly in the middle between start and end
    mid_lat1 = start_pt[0] + (end_pt[0] - start_pt[0]) * 0.33
    mid_lon1 = start_pt[1] + (end_pt[1] - start_pt[1]) * 0.33
    mid_lat2 = start_pt[0] + (end_pt[0] - start_pt[0]) * 0.66
    mid_lon2 = start_pt[1] + (end_pt[1] - start_pt[1]) * 0.66
    mid_pts = [(mid_lat1, mid_lon1), (mid_lat2, mid_lon2)]

    print(f"Vehicle   : {VEHICLE_ID}")
    print(f"Simulating: 2 trips to test violation (Max = 1)")
    print("-" * 55)

    try:
        reset_req = urllib.request.Request(f"{SERVER_URL}/reset_trips", method="POST")
        urllib.request.urlopen(reset_req, timeout=5, context=ctx)
        print("Backend state reset successfully.")
    except Exception as e:
        print(f"Reset failed: {e}")

    for trip in range(1, 3):
        result = simulate_one_trip(trip, start_pt, mid_pts, end_pt)
        status = result.get("status", "")

        if "VIOLATION" in status:
            print(f"\n{'='*55}")
            print(f"VIOLATION DETECTED after Trip #{trip}!")
            print(f"Telegram alert should have been sent!")
            print(f"{'='*55}")
            break

        time.sleep(1)

    print(f"\n{'='*55}")
    print("Simulation stopped! Check your Telegram for the alert.")
    print(f"{'='*55}")

if __name__ == "__main__":
    main()
