import requests
import pandas as pd
import time

# NASA POWER API endpoint
BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Major Indian Ports
PORTS = {
    "Mumbai": (18.9490, 72.8400),
    "JNPT": (18.9400, 72.9500),
    "Kandla": (23.0333, 70.2167),
    "Mormugao": (15.4130, 73.8000),
    "New_Mangalore": (12.9141, 74.8560),
    "Kochi": (9.9667, 76.2667),
    "Tuticorin": (8.7642, 78.1348),
    "Chennai": (13.0827, 80.2707),
    "Ennore": (13.2500, 80.3500),
    "Visakhapatnam": (17.6868, 83.2185),
    "Paradip": (20.3167, 86.6167),
    "Kolkata": (22.5726, 88.3639),
    "Haldia": (22.0250, 88.0600),
    "Port_Blair": (11.6234, 92.7265),
    "Dhamra": (20.7820, 86.9850),
    "Krishnapatnam": (14.2500, 80.1200),
    "Hazira": (21.1167, 72.6500),
    "Mundra": (22.8390, 69.7210)
}

PARAMETERS = "T2M,PRECTOTCORR,WS10M"

all_data = []

for port, (lat, lon) in PORTS.items():

    print(f"Downloading {port}...")

    params = {
        "parameters": PARAMETERS,
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": "20200101",
        "end": "20251231",
        "format": "JSON"
    }

    response = requests.get(BASE_URL, params=params)

    if response.status_code != 200:
        print(f"Skipping {port}")
        continue

    weather = response.json()["properties"]["parameter"]

    df = pd.DataFrame({
        "Date": weather["T2M"].keys(),
        "Temperature": weather["T2M"].values(),
        "Rainfall": weather["PRECTOTCORR"].values(),
        "WindSpeed": weather["WS10M"].values()
    })

    df["Port"] = port

    all_data.append(df)

    time.sleep(1)

# Combine all ports
final_df = pd.concat(all_data, ignore_index=True)

# Convert dates
final_df["Date"] = pd.to_datetime(final_df["Date"], format="%Y%m%d")

# Save CSV
output_file = "data/raw/india_ports_weather_2020_2025.csv"

final_df.to_csv(output_file, index=False)

print("\nDone!")
print(f"Rows: {len(final_df)}")
print(f"Saved to: {output_file}")