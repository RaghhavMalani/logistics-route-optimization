import pandas as pd

# Load the raw weather dataset
df = pd.read_csv("data/raw/india_ports_weather_2020_2025.csv")

print("=" * 60)
print("DATASET SHAPE")
print("=" * 60)
print(df.shape)

print("\n")

print("=" * 60)
print("DATASET INFO")
print("=" * 60)
print(df.info())

print("\n")

print("=" * 60)
print("FIRST 5 ROWS")
print("=" * 60)
print(df.head())

print("\n")

print("=" * 60)
print("LAST 5 ROWS")
print("=" * 60)
print(df.tail())

print("\n")

print("=" * 60)
print("COLUMN NAMES")
print("=" * 60)
print(df.columns.tolist())

print("\n")

print("=" * 60)
print("MISSING VALUES")
print("=" * 60)
print(df.isnull().sum())

print("\n")

print("=" * 60)
print("UNIQUE PORTS")
print("=" * 60)
print(df["Port"].unique())

print("\n")

print("=" * 60)
print("NUMBER OF UNIQUE PORTS")
print("=" * 60)
print(df["Port"].nunique())

print("\n")

print("=" * 60)
print("SUMMARY STATISTICS")
print("=" * 60)
print(df.describe())