import pandas as pd
import glob
import json
from pathlib import Path

folder = "/app/data"

files = glob.glob(f"{folder}/*.json")

dfs = []
for f in files:
    print(f"Reading: {f}", flush=True)
    df = pd.read_json(f)
    df["source_file"] = Path(f).name
    dfs.append(df)

result = pd.concat(dfs, ignore_index=True)
print(result.head())
result.to_csv("/app/data/full_output.csv")