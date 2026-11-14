"""Load football-data.co.uk CSVs, validate them, and reshape odds to a long format.

Wide input: one row per match, with columns like B365H/B365D/B365A (pre-closing odds) and
B365CH/B365CD/B365CA (closing odds). Long output: one row per (match, bookmaker, snapshot).
"""

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# Explicit code -> bookmaker map, taken from football-data.co.uk/notes.txt.
# We do NOT infer bookmakers from column suffixes: e.g. "BFD" is Betfair *draw*,
# while "BFDH" is *Betfred* home. "VC" (VC Bet) was renamed BetVictor, now coded "BV".
# Max/Avg are market aggregates, not bookmakers, so they are deliberately left out.
BOOKMAKERS: dict[str, str] = {
    "1XB": "1xBet",
    "B365": "Bet365",
    "BF": "Betfair Sportsbook",
    "BFD": "Betfred",
    "BFE": "Betfair Exchange",
    "BMGM": "BetMGM",
    "BV": "BetVictor",
    "BW": "Bet&Win",
    "CL": "Coral",
    "IW": "Interwetten",
    "LB": "Ladbrokes",
    "PP": "Paddy Power",
    "PS": "Pinnacle",
    "SKB": "Sky Bet",
    "VC": "BetVictor",
    "WH": "William Hill",
}

# Non-"C" columns are what football-data calls "pre-closing" odds (an earlier snapshot,
# not a true market open). We label them 'open' for brevity; see README.
SNAPSHOTS: dict[str, str] = {"open": "", "close": "C"}

LONG_COLUMNS = [
    "match_id",
    "season",
    "date",
    "home",
    "away",
    "bookmaker",
    "snapshot",
    "odds_h",
    "odds_d",
    "odds_a",
    "result",
]
KEY = ["match_id", "bookmaker", "snapshot"]


def read_season(path: Path) -> pd.DataFrame:
    """Read one season CSV and validate the match-level columns (date, teams, result)."""
    # .copy() consolidates the 100+ column frame so adding columns is cheap.
    df = pd.read_csv(path, encoding="utf-8-sig").copy()  # files start with a UTF-8 BOM
    n = len(df)
    df["date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    valid = (
        df["date"].notna()
        & df["HomeTeam"].notna()
        & df["AwayTeam"].notna()
        & df["FTR"].isin(["H", "D", "A"])
    )
    df = df[valid].copy()
    if n - len(df):
        log.warning(
            "%s: dropped %d of %d matches (bad date/teams/result)", path.name, n - len(df), n
        )

    df["season"] = path.stem.split("_")[-1]  # "E0_2526.csv" -> "2526"
    df["match_id"] = (
        df["Div"]
        + "_"
        + df["date"].dt.strftime("%Y-%m-%d")
        + "_"
        + df["HomeTeam"].str.replace(" ", "_")
        + "_"
        + df["AwayTeam"].str.replace(" ", "_")
    )
    return df


def to_long(wide: pd.DataFrame, source: str = "") -> pd.DataFrame:
    """Reshape wide bookmaker columns into one row per (match, bookmaker, snapshot).

    A missing or invalid price only drops that bookmaker's row, never the whole match.
    """
    parts = []
    for code, name in BOOKMAKERS.items():
        for snapshot, suffix in SNAPSHOTS.items():
            cols = [f"{code}{suffix}{o}" for o in "HDA"]
            if not all(c in wide.columns for c in cols):
                continue  # this bookmaker/snapshot is not in this file
            part = wide[["match_id", "season", "date", "HomeTeam", "AwayTeam", "FTR", *cols]]
            part = part.rename(
                columns={
                    "HomeTeam": "home",
                    "AwayTeam": "away",
                    "FTR": "result",
                    cols[0]: "odds_h",
                    cols[1]: "odds_d",
                    cols[2]: "odds_a",
                }
            )
            part = part.assign(bookmaker=name, snapshot=snapshot)
            parts.append(part)

    if not parts:
        raise ValueError(f"{source}: no known bookmaker odds columns found")
    long = pd.concat(parts, ignore_index=True)[LONG_COLUMNS]

    odds_cols = ["odds_h", "odds_d", "odds_a"]
    long[odds_cols] = long[odds_cols].apply(pd.to_numeric, errors="coerce")
    missing = long[odds_cols].isna().any(axis=1)
    invalid = ~missing & (long[odds_cols] <= 1.0).any(axis=1)  # odds <= 1 are impossible
    long = long[~missing & ~invalid]
    # Guard against two codes mapping to the same bookmaker in one file (e.g. VC and BV).
    dupes = long.duplicated(KEY)
    long = long[~dupes].reset_index(drop=True)
    log.info(
        "%s: %d odds rows kept, dropped %d missing, %d with odds <= 1, %d duplicates",
        source,
        len(long),
        int(missing.sum()),
        int(invalid.sum()),
        int(dupes.sum()),
    )
    return long


def load_files(paths: list[Path]) -> pd.DataFrame:
    """Load and reshape several season files into one long DataFrame."""
    if not paths:
        raise FileNotFoundError("no CSV files given")
    frames = [to_long(read_season(p), source=p.name) for p in sorted(paths)]
    return pd.concat(frames, ignore_index=True)


def load_dir(raw_dir: Path) -> pd.DataFrame:
    """Load every E0_*.csv in a directory."""
    paths = sorted(raw_dir.glob("E0_*.csv"))
    if not paths:
        raise FileNotFoundError(f"no E0_*.csv files in {raw_dir}; run `python cli.py download`")
    return load_files(paths)
