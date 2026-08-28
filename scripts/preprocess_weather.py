import pandas as pd
from sklearn.preprocessing import StandardScaler
import joblib
import os
# -----------------------------------
# Load raw weather dataset
# -----------------------------------
df = pd.read_csv("data/raw/india_ports_weather_2020_2025.csv")

print(f"Original Shape: {df.shape}")

# -----------------------------------
# Convert Date column
# -----------------------------------
df["Date"] = pd.to_datetime(df["Date"])

# -----------------------------------
# Aggregate weather across all ports
# -----------------------------------
daily_weather = (
    df.groupby("Date")[["Temperature", "Rainfall", "WindSpeed"]]
      .mean()
      .reset_index()
)

# -----------------------------------
# Sort by Date
# -----------------------------------
daily_weather = daily_weather.sort_values("Date")
# -----------------------------------
# Create 7-day Rolling Features
# -----------------------------------

daily_weather["temp_rolling7"] = (
    daily_weather["Temperature"]
    .rolling(window=7)
    .mean()
)

daily_weather["rain_rolling7"] = (
    daily_weather["Rainfall"]
    .rolling(window=7)
    .mean()
)

daily_weather["wind_rolling7"] = (
    daily_weather["WindSpeed"]
    .rolling(window=7)
    .mean()
)

print("\nRolling features created successfully!\n")

# -----------------------------------
# Create 7-day Lag Features
# -----------------------------------

daily_weather["temp_lag7"] = daily_weather["Temperature"].shift(7)
daily_weather["rain_lag7"] = daily_weather["Rainfall"].shift(7)
daily_weather["wind_lag7"] = daily_weather["WindSpeed"].shift(7)

# -----------------------------------
# Create 14-day Lag Features
# -----------------------------------

daily_weather["temp_lag14"] = daily_weather["Temperature"].shift(14)
daily_weather["rain_lag14"] = daily_weather["Rainfall"].shift(14)
daily_weather["wind_lag14"] = daily_weather["WindSpeed"].shift(14)

print("\nLag features created successfully!\n")

print(daily_weather.head(10))

print(f"Aggregated Shape: {daily_weather.shape}")

print("\nFirst 20 rows:\n")
print(daily_weather.head(20))

# -----------------------------------
# Remove rows with NaN values
# -----------------------------------

daily_weather = daily_weather.dropna().reset_index(drop=True)

# -----------------------------------
# Save unscaled weather features
# -----------------------------------

unscaled_path = "data/intermediate/weather_features_unscaled_2020_2025.csv"

daily_weather.to_csv(unscaled_path, index=False)

print("\nUnscaled dataset saved successfully!")
print(f"Location: {unscaled_path}")

print("\nDataset after removing NaN rows:")
print(daily_weather.shape)


# -----------------------------------
# Scale numerical weather features
# -----------------------------------

scaler = StandardScaler()

columns_to_scale = [
    "Temperature",
    "Rainfall",
    "WindSpeed",
    "temp_rolling7",
    "rain_rolling7",
    "wind_rolling7",
    "temp_lag7",
    "rain_lag7",
    "wind_lag7",
    "temp_lag14",
    "rain_lag14",
    "wind_lag14"
]

daily_weather[columns_to_scale] = scaler.fit_transform(
    daily_weather[columns_to_scale]
)

# -----------------------------------
# Save fitted scaler
# -----------------------------------

os.makedirs("models", exist_ok=True)

joblib.dump(
    scaler,
    "models/weather_scaler.pkl"
)

print("\nWeather scaler saved successfully!")

print("\nScaling completed successfully!")

print("\nScaling completed successfully!")

print("\nDataset Shape:")
print(daily_weather.shape)

# -----------------------------------
# Save preprocessed dataset
# -----------------------------------

output_path = "data/preprocessed/weather_preprocessed_2020_2025.csv"

daily_weather.to_csv(output_path, index=False)

print("\nFirst five rows after scaling:\n")
print(daily_weather.describe())

print("\nPreprocessed weather dataset saved successfully!")
print(f"Location: {output_path}")