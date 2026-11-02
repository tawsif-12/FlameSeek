"""Day partitions: <root>/<stage>/year=YYYY/month=MM/day=DD/part.parquet.

Every stage reads and writes one partition per day. Writes are atomic (temp file then
rename), so an interrupted run never leaves a half-written partition that a later
incremental run would skip. Cross-day reads go through DuckDB.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

STAGES = ("raw_daily", "detections", "lowconf", "removed", "day_stats", "assign", "event_state", "merges",
          "link_stats", "grid_overpass", "grid_cellday")


def part_dir(root: Path, stage: str, day: date) -> Path:
    return Path(root) / stage / f"year={day:%Y}" / f"month={day:%m}" / f"day={day:%d}"


def part_file(root: Path, stage: str, day: date) -> Path:
    return part_dir(root, stage, day) / "part.parquet"


def exists(root: Path, stage: str, day: date) -> bool:
    return part_file(root, stage, day).exists()


def write(df: pd.DataFrame, root: Path, stage: str, day: date) -> Path:
    """Atomic write. An empty frame is still written, so "processed, nothing found" differs
    from "not processed"."""
    f = part_file(root, stage, day)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".tmp{os.getpid()}")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, f)
    return f


def read(root: Path, stage: str, day: date, columns=None) -> pd.DataFrame | None:
    f = part_file(root, stage, day)
    if not f.exists():
        return None
    df = pd.read_parquet(f)  # partitions are one day each, so reading whole files is cheap
    if df.empty:
        return df
    return df[columns] if columns else df


def days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def glob_for(root: Path, stage: str, start: date, end: date) -> list[str]:
    """Existing, non-empty partition files of a stage between two days (inclusive)."""
    import pyarrow.parquet as pq
    return [str(part_file(root, stage, d)) for d in days(start, end)
            if exists(root, stage, d) and pq.read_metadata(part_file(root, stage, d)).num_rows > 0]


def duck(root: Path, stage: str, start: date, end: date, sql: str = "SELECT * FROM t", con=None) -> pd.DataFrame:
    """Run SQL over a stage's partitions in [start, end]; the partitions are exposed as table t."""
    import duckdb
    # Empty days are written as zero-row files; glob_for skips them (DuckDB cannot read them).
    files = glob_for(root, stage, start, end)
    if not files:
        return pd.DataFrame()
    c = con or connect()
    c.execute(f"CREATE OR REPLACE TEMP VIEW t AS SELECT * FROM read_parquet({files!r}, union_by_name=true)")
    out = c.execute(sql).df()
    if con is None:
        c.close()
    return out


def connect():
    """DuckDB connection pinned to UTC. Without this DuckDB returns timestamps converted to the
    computer's local time zone, which would put local times into *_utc columns."""
    import duckdb
    c = duckdb.connect()
    c.execute("SET TimeZone = 'UTC'")
    return c
