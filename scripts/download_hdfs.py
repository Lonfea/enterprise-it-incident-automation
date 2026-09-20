from pathlib import Path

import requests

URL = "https://raw.githubusercontent.com/logpai/loghub/master/HDFS/HDFS_2k.log"
TARGET = Path("data/HDFS_2k.log")

TARGET.parent.mkdir(exist_ok=True)
response = requests.get(URL, timeout=30)
response.raise_for_status()
TARGET.write_bytes(response.content)
print(f"Downloaded {TARGET} ({TARGET.stat().st_size:,} bytes)")
