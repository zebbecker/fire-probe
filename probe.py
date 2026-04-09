"""Probe the OGC Features API for wildland fire perimeter data availability."""

import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://openveda.cloud/api/features"

COLLECTIONS = [
    "public.eis_fire_lf_perimeter_nrt",
    "public.eis_fire_lf_newfirepix_nrt",
    "public.eis_fire_lf_fireline_nrt",
]

CSV_PATH = Path("data/probe-results.csv")
CSV_FIELDNAMES = [
    "probe_time",
    "http_status",
    "response_time_ms",
    "newest_feature_datetime",
    "collection_id",
]

TIMEOUT = 30  # seconds


def _extract_newest_t(features: list) -> str:
    """Return the newest FEDS timestep string from features.

    The 't' field is a FEDS TimeStep in approximate local solar time
    (AM overpasses → 00:00:00, PM overpasses → 12:00:00). It is not a
    UTC timestamp and carries no timezone. Lexicographic max is correct
    since all values share the same format.
    """
    timestamps = [t for f in features if (t := f.get("properties", {}).get("t"))]
    return max(timestamps) if timestamps else ""


def probe_collection(session: requests.Session, collection_id: str) -> dict:
    """Probe a single collection and return one result row."""
    probe_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    url = f"{BASE_URL}/collections/{collection_id}/items"
    http_status: int | str = ""
    response_time_ms = 0
    newest_feature_datetime = ""

    t0 = time.monotonic()
    try:
        resp = session.get(
            url, params={"f": "geojson", "limit": 1, "sortby": "-t"}, timeout=TIMEOUT
        )
        response_time_ms = round((time.monotonic() - t0) * 1000)

        # Fall back if sortby is unsupported — fetch recent features and find max t client-side
        if resp.status_code in (400, 422):
            t0 = time.monotonic()
            resp = session.get(
                url,
                params={"f": "geojson", "limit": 100},
                timeout=TIMEOUT,
            )
            response_time_ms = round((time.monotonic() - t0) * 1000)

        http_status = resp.status_code
        if resp.status_code == 200:
            try:
                features = resp.json().get("features", [])
                newest_feature_datetime = _extract_newest_t(features)
            except ValueError as e:
                # Non-JSON body (e.g. HTML error page) — preserve the HTTP status
                print(f"  Warning: could not parse JSON ({e})")
                print(f"  Response preview: {resp.text[:300]!r}")

    except requests.Timeout:
        response_time_ms = round((time.monotonic() - t0) * 1000)
        http_status = "TIMEOUT"
    except requests.RequestException as e:
        response_time_ms = round((time.monotonic() - t0) * 1000)
        http_status = f"ERROR:{type(e).__name__}"

    return {
        "probe_time": probe_time,
        "http_status": http_status,
        "response_time_ms": response_time_ms,
        "newest_feature_datetime": newest_feature_datetime,
        "collection_id": collection_id,
    }


def append_rows(rows: list[dict], csv_path: Path = CSV_PATH) -> None:
    """Append result rows to the CSV, creating the file with headers if needed."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = []
    with requests.Session() as session:
        for collection_id in COLLECTIONS:
            row = probe_collection(session, collection_id)
            rows.append(row)
            print(
                f"{collection_id}: status={row['http_status']} "
                f"latency={row['response_time_ms']}ms "
                f"newest={row['newest_feature_datetime']}"
            )
    append_rows(rows)


if __name__ == "__main__":
    main()
