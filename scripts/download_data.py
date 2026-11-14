"""Download Premier League (E0) season CSVs from football-data.co.uk into data/raw/.

URL pattern verified against the index page https://football-data.co.uk/englandm.php,
which links to relative paths like "mmz4281/2526/E0.csv".

Idempotent: files that already exist are skipped. Polite: one request at a time with a pause.
Exits with a non-zero status and a clear message if any download fails.
"""

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://football-data.co.uk/mmz4281/{season}/E0.csv"
DEFAULT_SEASONS = ["2324", "2425", "2526"]
PAUSE_SECONDS = 2.0
USER_AGENT = "odds-monitor-prototype/0.1 (historical research script)"


def download_season(season: str, out_dir: Path) -> bool:
    """Download one season; return True if a request was made, False if skipped."""
    target = out_dir / f"E0_{season}.csv"
    if target.exists():
        print(f"skip  {target.name} (already exists)")
        return False

    url = BASE_URL.format(season=season)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        sys.exit(f"FAIL  {url} -> HTTP {exc.code}. Download it manually into {out_dir}/")
    except urllib.error.URLError as exc:
        sys.exit(f"FAIL  {url} -> network error: {exc.reason}. Download it manually.")

    # Sanity check: a real file starts with the "Div" header (optionally after a UTF-8 BOM).
    if status != 200 or not body.lstrip(b"\xef\xbb\xbf").startswith(b"Div,"):
        sys.exit(f"FAIL  {url} -> HTTP {status}, response does not look like an E0 CSV")

    # Write to a temp file then rename, so a crash never leaves a partial file that
    # would be wrongly "skipped" on the next run.
    partial = target.with_suffix(".part")
    partial.write_bytes(body)
    partial.replace(target)
    print(f"ok    {target.name} <- {url} (HTTP {status}, {len(body):,} bytes)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS, help="e.g. 2324 2425")
    parser.add_argument("--out-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for i, season in enumerate(args.seasons):
        made_request = download_season(season, args.out_dir)
        if made_request and i < len(args.seasons) - 1:
            time.sleep(PAUSE_SECONDS)


if __name__ == "__main__":
    main()
