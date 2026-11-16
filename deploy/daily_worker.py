"""Run ingestion immediately and once per UTC day, retrying failures after an hour."""
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone


def main():
    while True:
        result = subprocess.run([sys.executable, '-m', 'pipeline.daily', 'run'], check=False)
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        delay = (next_run - now).total_seconds() if result.returncode == 0 else 3600
        print(f'Daily ingestion exited {result.returncode}; next attempt in {delay:.0f}s', flush=True)
        time.sleep(delay)


if __name__ == '__main__':
    main()
