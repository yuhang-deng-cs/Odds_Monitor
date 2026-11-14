from db import connect, ingest
from load import load_dir


def test_ingest_is_idempotent(raw_dir, tmp_path):
    con = connect(tmp_path / "test.duckdb")
    long = load_dir(raw_dir)

    first = ingest(con, long)
    assert first == {"matches": 3, "odds_snapshots": 10}

    second = ingest(con, load_dir(raw_dir))  # re-run: nothing new
    assert second == {"matches": 0, "odds_snapshots": 0}
    assert con.execute("SELECT count(*) FROM odds_snapshots").fetchall()[0][0] == 10


def test_ingest_persists_across_connections(raw_dir, tmp_path):
    path = tmp_path / "test.duckdb"
    con = connect(path)
    ingest(con, load_dir(raw_dir))
    con.close()
    con = connect(path)  # schema creation must not wipe data
    assert ingest(con, load_dir(raw_dir)) == {"matches": 0, "odds_snapshots": 0}
    assert con.execute("SELECT count(*) FROM matches").fetchall()[0][0] == 3
