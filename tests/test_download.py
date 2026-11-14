"""Downloader behaviour without touching the network."""

import io

import pytest

import download


class _Response(io.BytesIO):
    status = 200


def _serve(body: bytes):
    return lambda request, timeout: _Response(body)


def test_existing_file_is_skipped(tmp_path, monkeypatch):
    (tmp_path / "E0_2425.csv").write_text("Div,Date\n", encoding="utf-8")
    monkeypatch.setattr(download.urllib.request, "urlopen", pytest.fail)  # must not be called
    assert download.download_season("2425", tmp_path) is False


def test_valid_csv_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(download.urllib.request, "urlopen", _serve(b"\xef\xbb\xbfDiv,Date\nE0,x\n"))
    assert download.download_season("2425", tmp_path) is True
    assert (tmp_path / "E0_2425.csv").read_bytes().endswith(b"E0,x\n")
    assert not list(tmp_path.glob("*.part"))


def test_html_error_page_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(download.urllib.request, "urlopen", _serve(b"<html>not found</html>"))
    with pytest.raises(download.DownloadError, match="does not look like an E0 CSV"):
        download.download_season("2425", tmp_path)
    assert not (tmp_path / "E0_2425.csv").exists()
