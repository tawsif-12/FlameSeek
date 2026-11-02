"""Download archived TLEs from Space-Track for a historical processing window.

Usage (PowerShell):
    $env:SPACETRACK_USER = "you@example.org"
    $env:SPACETRACK_PASSWORD = "..."
    E:\\anaconda\\envs\\flameseek\\python.exe tools\\fetch_spacetrack_tle.py --start 2016-10-26 --end 2016-11-06

Writes data/raw/tle/<year>/spacetrack_gp_history_<start>_<end>.3le for Terra (25994),
Aqua (27424) and S-NPP (37849) by default. The pipeline (pipeline/tle_archive.py) picks
the epoch nearest each window midpoint.

Credentials are read only from the environment. They are sent in the login POST body
and are never written to disk, printed, or logged. Error messages do not echo the
request body or response bodies that might contain them.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.space-track.org"
DEFAULT_IDS = {"Terra": 25994, "Aqua": 27424, "S-NPP": 37849}
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", required=True, help="first epoch day, YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", required=True, help="last epoch day, YYYY-MM-DD (exclusive)")
    ap.add_argument("--ids", default=",".join(map(str, DEFAULT_IDS.values())),
                    help="comma-separated NORAD catalog ids")
    ap.add_argument("--out-dir", default=None, help="default: data/raw/tle/<start year>/")
    a = ap.parse_args()

    user, password = os.environ.get("SPACETRACK_USER"), os.environ.get("SPACETRACK_PASSWORD")
    if not user or not password:
        print("Set SPACETRACK_USER and SPACETRACK_PASSWORD in the environment.", file=sys.stderr)
        return 2

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "FlameSeek/1.0 (research pipeline)")]
    body = urllib.parse.urlencode({"identity": user, "password": password}).encode()
    del password
    try:
        with opener.open(f"{BASE}/ajaxauth/login", data=body, timeout=60) as r:
            reply = r.read().decode(errors="replace")
        if "Failed" in reply:
            print("Space-Track login failed (check the credentials).", file=sys.stderr)
            return 1
    except urllib.error.URLError as exc:
        print(f"Space-Track login request failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        body = None

    query = (f"{BASE}/basicspacedata/query/class/gp_history/NORAD_CAT_ID/{a.ids}"
             f"/EPOCH/{a.start}--{a.end}/orderby/NORAD_CAT_ID,EPOCH%20asc/format/3le")
    try:
        with opener.open(query, timeout=300) as r:
            text = r.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        print(f"Space-Track query failed: HTTP {exc.code}", file=sys.stderr)
        return 1
    finally:
        try:
            opener.open(f"{BASE}/ajaxauth/logout", timeout=30).close()
        except Exception:
            pass

    n = sum(1 for ln in text.splitlines() if ln.startswith("1 "))
    if not n:
        print("No TLEs returned for that range.", file=sys.stderr)
        return 1
    out_dir = Path(a.out_dir) if a.out_dir else ROOT / "data" / "raw" / "tle" / a.start[:4]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"spacetrack_gp_history_{a.start}_{a.end}.3le"
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {n} TLEs to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
