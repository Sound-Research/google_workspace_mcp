"""Tests for batch_get_drive_file_content."""

import json
from unittest.mock import Mock, patch

import pytest

from gdrive.drive_tools import batch_get_drive_file_content


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class _FakeDownloader:
    """Fake MediaIoBaseDownload that writes preset bytes into the BytesIO handle."""

    def __init__(self, fh, data):
        fh.write(data)
        fh.seek(0)

    def next_chunk(self):
        return None, True


def _patch_downloader(content_bytes):
    return patch(
        "gdrive.drive_tools.MediaIoBaseDownload",
        side_effect=lambda fh, req: _FakeDownloader(fh, content_bytes),
    )


def _make_resolve_side_effect(file_map):
    """Return a side-effect coroutine for resolve_drive_item keyed by file_id."""

    async def _resolve(service, file_id, extra_fields=None, max_depth=5):
        return file_id, file_map[file_id]

    return _resolve


# ---------------------------------------------------------------------------
# Happy-path: all files succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_all_succeed():
    file_map = {
        "id1": {
            "name": "Doc One",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "https://drive.google.com/file/id1",
        },
        "id2": {
            "name": "Sheet Two",
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "webViewLink": "https://drive.google.com/file/id2",
        },
    }
    mock_service = Mock()
    mock_service.files().export_media.return_value = "req"

    with (
        patch(
            "gdrive.drive_tools.resolve_drive_item",
            side_effect=_make_resolve_side_effect(file_map),
        ),
        _patch_downloader(b"hello content"),
    ):
        raw = await _unwrap(batch_get_drive_file_content)(
            service=mock_service,
            user_google_email="user@example.com",
            file_ids=["id1", "id2"],
        )

    results = json.loads(raw)
    assert len(results) == 2

    assert results[0]["id"] == "id1"
    assert results[0]["name"] == "Doc One"
    assert results[0]["error"] is None
    assert "--- CONTENT ---" in results[0]["content"]
    assert "hello content" in results[0]["content"]

    assert results[1]["id"] == "id2"
    assert results[1]["error"] is None


# ---------------------------------------------------------------------------
# Per-file error: one file fails, rest succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_partial_failure():
    file_map = {
        "good": {
            "name": "Good File",
            "mimeType": "text/plain",
            "webViewLink": "https://drive.google.com/file/good",
        },
    }

    async def _resolve_with_error(service, file_id, extra_fields=None, max_depth=5):
        if file_id == "bad":
            raise Exception("File not found")
        return file_id, file_map[file_id]

    mock_service = Mock()
    mock_service.files().get_media.return_value = "req"

    with (
        patch(
            "gdrive.drive_tools.resolve_drive_item",
            side_effect=_resolve_with_error,
        ),
        _patch_downloader(b"some text"),
    ):
        raw = await _unwrap(batch_get_drive_file_content)(
            service=mock_service,
            user_google_email="user@example.com",
            file_ids=["good", "bad"],
        )

    results = json.loads(raw)
    assert len(results) == 2

    good = next(r for r in results if r["id"] == "good")
    assert good["error"] is None
    assert good["content"] is not None

    bad = next(r for r in results if r["id"] == "bad")
    assert bad["error"] == "File not found"
    assert bad["content"] is None
    assert bad["name"] is None


# ---------------------------------------------------------------------------
# Result order matches input order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_preserves_input_order():
    ids = ["z", "a", "m"]
    file_map = {
        fid: {
            "name": f"File {fid}",
            "mimeType": "text/plain",
            "webViewLink": f"https://drive.google.com/file/{fid}",
        }
        for fid in ids
    }
    mock_service = Mock()
    mock_service.files().get_media.return_value = "req"

    with (
        patch(
            "gdrive.drive_tools.resolve_drive_item",
            side_effect=_make_resolve_side_effect(file_map),
        ),
        _patch_downloader(b"x"),
    ):
        raw = await _unwrap(batch_get_drive_file_content)(
            service=mock_service,
            user_google_email="user@example.com",
            file_ids=ids,
        )

    results = json.loads(raw)
    assert [r["id"] for r in results] == ids


# ---------------------------------------------------------------------------
# Empty file_ids list returns empty array
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_empty_ids():
    mock_service = Mock()

    raw = await _unwrap(batch_get_drive_file_content)(
        service=mock_service,
        user_google_email="user@example.com",
        file_ids=[],
    )

    assert json.loads(raw) == []
