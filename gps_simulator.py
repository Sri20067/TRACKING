"""
GPS Simulator - Simulates a vehicle moving between Excavation Zone and Dump Zone.
Run this while the Flask server is running to see the vehicle move on the dashboard map.
"""

import requests
import time
import random
from datetime import datetime

SERVER_URL = "http://127.0.0.1:5000/send_gps"
VEHICLE_ID = "TN09AB1234"

# Waypoints: Excavation Zone -> Route -> Dump Zone -> Route -> Excavation Zone (loop)
ROUTE = [
    # Start in Excavation Zone
    (13.0820, 80.2670),
    (13.0825, 80.2675),
    (13.0830, 80.2680),
    (13.0835, 80.2685),
    # Moving toward Dump Zone
    (13.0840, 80.2690),
    (13.0845, 80.2695),
    (13.0850, 80.2700),
    (13.0855, 80.2710),
    (13.0860, 80.2720),
    (13.0865, 80.2730),
    (13.0870, 80.2740),
    (13.0875, 80.2745),
    (13.0880, 80.2750),
    (13.0885, 80.2755),
    (13.0890, 80.2760),
    (13.0895, 80.2765),
    (13.0900, 80.2770),
    # Arriving at Dump Zone
    (13.0910, 80.2775),
    (13.0920, 80.2780),
    (13.0930, 80.2785),
    (13.0940, 80.2790),
    # Pause at dump zone, then return
    (13.0935, 80.2785),
    (13.0925, 80.2780),
    (13.0915, 80.2770),
    (13.0905, 80.2760),
    (13.0895, 80.2750),
    (13.0885, 80.2740),
    (13.0875, 80.2730),
    (13.0865, 80.2720),
    (13.0855, 80.2710),
    (13.0845, 80.2700),
    (13.0840, 80.2695),
    (13.0835, 80.2690),
    (13.0830, 80.2685),
    (13.0825, 80.2680),
    # Back at Excavation Zone
    (13.0820, 80.2670),
]

def add_noise(lat, lon):
    """Add small random noise to simulate real GPS jitter."""
    return (
        lat + random.uniform(-0.0002, 0.0002),
        lon + random.uniform(-0.0002, 0.0002)
    )

def send_gps(lat, lon):
    """Send a GPS coordinate to the server."""
    data = {
        "vehicle_id": VEHICLE_ID,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "timestamp": datetime.now().isoformat()
    }
    try:
        resp = requests.post(SERVER_URL, json=data, timeout=5)
        result = resp.json()
        status = result.get("status", "?")
        trips = result.get("trip_count", "?")
        print(f"  📡 Sent ({data['latitude']}, {data['longitude']}) -> {status} | Trips: {trips}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

def main():
    print("=" * 55)
    print("🚛  GPS SIMULATOR - Vehicle Route Simulation")
    print("=" * 55)
    print(f"Vehicle : {VEHICLE_ID}")
    print(f"Server  : {SERVER_URL}")
    print(f"Route   : {len(ROUTE)} waypoints per trip (loop)")
    print(f"Interval: 2 seconds between points")
    print("-" * 55)
    print("Open http://127.0.0.1:5000/dashboard to watch live!")
    print("-" * 55)
    print()

    trip_num = 1
    while True:
        print(f"🔄 Trip #{trip_num} starting...")
        for i, (lat, lon) in enumerate(ROUTE):
            noisy_lat, noisy_lon = add_noise(lat, lon)
            send_gps(noisy_lat, noisy_lon)
            time.sleep(2)

        print(f"✅ Trip #{trip_num} complete!\n")
        trip_num += 1
        time.sleep(3)  # Brief pause between trips

if __name__ == "__main__":
    main()
