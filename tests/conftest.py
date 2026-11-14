from pathlib import Path

import pytest

# Three synthetic matches in football-data format (with the real files' UTF-8 BOM).
# Row 2: Bet365 home odds = 1.00 (invalid). Row 3: Bet365 draw odds missing.
SYNTHETIC_CSV = """﻿Div,Date,HomeTeam,AwayTeam,FTR,B365H,B365D,B365A,B365CH,B365CD,B365CA,PSH,PSD,PSA,PSCH,PSCD,PSCA,MaxH,MaxD,MaxA
E0,10/08/2024,Man City,Chelsea,H,1.50,4.20,6.50,1.45,4.40,7.00,1.53,4.50,6.90,1.48,4.70,7.40,1.55,4.60,7.50
E0,10/08/2024,Arsenal,Wolves,D,1.00,3.40,2.30,2.80,3.30,2.50,2.95,3.45,2.45,2.85,3.40,2.60,3.00,3.50,2.60
E0,11/08/2024,Everton,Brighton,A,2.90,,2.40,2.95,3.30,2.45,3.05,3.40,2.40,3.00,3.35,2.50,3.10,3.50,2.50
"""


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    (d / "E0_2425.csv").write_text(SYNTHETIC_CSV, encoding="utf-8")
    return d
