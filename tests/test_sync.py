"""Two independent computers, offline concurrent edits, persistent FSRS and Drive IO."""
import copy
import asyncio
import json
import threading
from datetime import datetime, timezone

import httpx
import pytest
from tests.local_client import TestClient

import app
import drive_sync
import sync_storage as storage
import instance_lock


def word(word_id="contract", text="contract", **extra):
    return {"id": word_id, "word": text, "notebook_id": "default", "phonetic": "",
            "definition": "n. 合同", "example": "A binding contract.",
            "created_at": "2026-10-18T08:00:00+00:00", **extra}


def ops(path):
    return list(storage.read(path)["_sync"]["operations"].values())


def engine(path, secrets):
    return drive_sync.DriveSync(lambda: path, threading.RLock(),
                                lambda: {"credentials_dir": str(secrets), "interval_seconds": 30})


def test_legacy_migration_preserves_schedule_and_original(tmp_path):
    path = tmp_path / "words.json"
    srs = storage.review_state(None, [{"id": "legacy", "rating": 3, "at": "2026-10-17T10:00:00Z"}])
    original = {"words": [word(srs=srs)]}
    path.write_text(json.dumps(original), encoding="utf-8")
    migrated = storage.read(path)
    assert migrated["words"][0]["srs"] == srs
    assert migrated["words"][0]["notebook_id"] == "default"
    assert json.loads(path.with_suffix(".json.legacy.bak").read_text()) == original
    assert storage.read(path) == migrated


def test_field_edits_merge_independently_and_converge(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    storage.commit(a, {"words": [word()]})
    storage.merge(b, ops(a))
    left, right = storage.read(a), storage.read(b)
    left["words"][0]["definition"] = "n. 法律上可执行的协议"
    right["words"][0]["example"] = "The contract is enforceable."
    storage.commit(a, left)
    storage.commit(b, right)
    storage.merge(a, ops(b))
    storage.merge(b, ops(a))
    assert storage.read(a)["words"] == storage.read(b)["words"]
    assert storage.read(a)["words"][0]["definition"] == "n. 法律上可执行的协议"
    assert storage.read(a)["words"][0]["example"] == "The contract is enforceable."


def test_same_field_conflict_is_deterministic_in_any_merge_order(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    storage.commit(a, {"words": [word()]})
    storage.merge(b, ops(a))
    for path, value in ((a, "法律定义"), (b, "金融定义")):
        data = storage.read(path)
        data["words"][0]["definition"] = value
        storage.commit(path, data)
    left, right = ops(a), ops(b)
    storage.merge(a, right)
    storage.merge(b, list(reversed(left)))
    assert storage.read(a)["words"] == storage.read(b)["words"]
    before = a.read_bytes()
    storage.merge(a, left + right)
    assert a.read_bytes() == before


def test_offline_review_events_are_both_preserved_and_replayed(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    storage.commit(a, {"words": [word()]})
    storage.merge(b, ops(a))
    for path, event in ((a, {"id": "review-a", "rating": 3, "at": "2026-10-18T10:00:00Z"}),
                        (b, {"id": "review-b", "rating": 1, "at": "2026-10-18T11:00:00Z"})):
        data = storage.read(path)
        data["words"][0]["review_history"] = [event]
        storage.commit(path, data)
    left, right = ops(a), ops(b)
    storage.merge(a, right)
    storage.merge(b, left)
    merged = storage.read(a)["words"][0]
    assert merged == storage.read(b)["words"][0]
    assert len(merged["review_history"]) == 2
    assert merged["srs"]["reps"] == 2
    assert merged["srs"]["lapses"] == 1
    assert merged["srs"] == storage.review_state(None, merged["review_history"])


def test_delete_wins_over_stale_offline_edit_and_review(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    storage.commit(a, {"words": [word()]})
    storage.merge(b, ops(a))
    data = storage.read(a)
    data["words"] = []
    storage.commit(a, data)
    data = storage.read(b)
    data["words"][0].update(definition="离线编辑", review_history=[{"id": "late", "rating": 4, "at": "2026-10-18T11:00:00Z"}])
    storage.commit(b, data)
    left, right = ops(a), ops(b)
    storage.merge(a, right)
    storage.merge(b, left)
    assert storage.read(a)["words"] == storage.read(b)["words"] == []


def test_corrupt_local_file_is_never_overwritten(tmp_path):
    path = tmp_path / "words.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="损坏"):
        storage.read(path)
    with pytest.raises(ValueError):
        storage.merge(path, [])
    assert path.read_text() == "{broken"


def test_invalid_remote_batch_cannot_partially_overwrite(tmp_path):
    path = tmp_path / "words.json"
    storage.commit(path, {"words": [word()]})
    before = path.read_bytes()
    valid = copy.deepcopy(ops(path)[0])
    valid.update(id="remote-id", clock=100, field="definition", value="remote")
    invalid = {**valid, "id": "bad", "field": "review", "value": {"id": "x", "rating": 5, "at": "bad"}}
    with pytest.raises(ValueError):
        storage.merge(path, [valid, invalid])
    assert path.read_bytes() == before


def test_folder_two_computers_restart_and_idempotency(tmp_path):
    folder = tmp_path / "drive"
    a, b = tmp_path / "pc-a.json", tmp_path / "pc-b.json"
    left, right = engine(a, tmp_path / "secrets-a"), engine(b, tmp_path / "secrets-b")
    left.configure_folder(str(folder))
    right.configure_folder(str(folder))
    storage.commit(a, {"words": [word()]})
    assert left.sync()["pushed"] > 0
    assert right.sync()["pulled"] > 0
    changed = storage.read(b)
    changed["words"].append(word("bond", "bond"))
    storage.commit(b, changed)
    assert right.sync()["pushed"] > 0
    assert left.sync()["pulled"] > 0
    assert storage.read(a)["words"] == storage.read(b)["words"]
    restarted = engine(a, tmp_path / "secrets-a")
    assert restarted.sync() == {"pulled": 0, "pushed": 0}
    assert restarted.status()["pending"] == 0


def test_unavailable_folder_keeps_offline_changes(tmp_path):
    folder, path = tmp_path / "drive", tmp_path / "words.json"
    sync = engine(path, tmp_path / "secrets")
    sync.configure_folder(str(folder))
    storage.commit(path, {"words": [word()]})
    before = path.read_bytes()
    folder.rename(tmp_path / "offline-drive")
    assert "error" in sync.sync()
    assert path.read_bytes() == before
    assert sync.status()["pending"] > 0
    (tmp_path / "offline-drive").rename(folder)
    assert sync.sync()["pushed"] > 0


class FakeDrive:
    def __init__(self):
        self.files = {}
        self.requests = []
        self.fail_upload_once = False

    def handle(self, request):
        self.requests.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "refreshed", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer refreshed"
        if request.url.path == "/drive/v3/files":
            assert request.url.params["spaces"] == "appDataFolder"
            return httpx.Response(200, json={"files": [{"id": key, "size": str(len(value))} for key, value in self.files.items()]})
        if request.url.path.startswith("/drive/v3/files/"):
            return httpx.Response(200, content=self.files[request.url.path.rsplit("/", 1)[1]])
        if request.url.path == "/upload/drive/v3/files":
            boundary = request.headers["Content-Type"].split("boundary=")[1].encode()
            parts = request.content.split(b"--" + boundary)
            metadata = json.loads(parts[1].split(b"\r\n\r\n", 1)[1].strip())
            assert metadata["parents"] == ["appDataFolder"]
            payload = parts[2].split(b"\r\n\r\n", 1)[1].strip()
            self.files[str(len(self.files) + 1)] = payload
            if self.fail_upload_once:
                self.fail_upload_once = False
                raise httpx.ReadTimeout("response lost after upload", request=request)
            return httpx.Response(200, json={"id": str(len(self.files))})
        raise AssertionError(str(request.url))


def connect_fake(sync):
    storage.atomic_write(sync.secrets_dir / "client_secret.json", {"installed": {"client_id": "test.apps.googleusercontent.com", "client_secret": "secret"}})
    storage.atomic_write(sync.secrets_dir / "token.json", {"access_token": "expired", "refresh_token": "refresh", "expires_at": 0})


def test_drive_api_refresh_upload_download_and_retry(tmp_path, monkeypatch):
    drive = FakeDrive()
    real_client = httpx.Client
    monkeypatch.setattr(drive_sync.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(drive.handle), **kwargs))
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    left, right = engine(a, tmp_path / "secret-a"), engine(b, tmp_path / "secret-b")
    connect_fake(left)
    connect_fake(right)
    storage.commit(a, {"words": [word()]})
    drive.fail_upload_once = True
    assert "error" in left.sync()
    assert left.status()["pending"] > 0
    # Upload succeeded but its response was lost. Pulling the immutable log recovers it.
    assert "error" not in left.sync()
    assert len(drive.files) == 1
    assert right.sync()["pulled"] > 0
    assert storage.read(a)["words"] == storage.read(b)["words"]
    assert right.sync() == {"pulled": 0, "pushed": 0}
    assert right.status()["pending"] == 0
    assert all(b"refresh_token" not in payload and b"client_secret" not in payload for payload in drive.files.values())


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "words.json"
    monkeypatch.setattr(app, "DATA_FILE", path)
    monkeypatch.setattr(app, "cloud", engine(path, tmp_path / "secrets"))
    monkeypatch.setattr(app.config, "_CONFIG", {"provider": "ollama", "ollama": {"url": "http://127.0.0.1:11434/api/generate", "model": "test"}})
    # No lifespan: these API checks must not contact a real local AI or Drive account.
    return TestClient(app.app)





def test_full_backup_roundtrip_preserves_review_history(client, tmp_path):
    created = client.post("/api/words", json={"word": "bond", "definition": "n. 债券"}).json()["word"]
    client.post(f"/api/words/{created['id']}/review", json={"rating": 4})
    backup = client.get("/api/library/export").json()
    target = tmp_path / "restored.json"
    storage.merge(target, backup["operations"])
    restored = storage.read(target)["words"][0]
    assert len(restored["review_history"]) == 1 and restored["srs"]["reps"] == 1
    assert client.post("/api/library/import", json=backup).json()["imported"] == 0


def test_origin_guard_and_input_validation(client):
    assert client.post("/api/words", json={"word": 123}).status_code == 422
    assert client.post("/api/words", json={"word": "bad"}, headers={"Origin": "https://example.org"}).status_code == 403
    assert client.get("/api/sync/status", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/sync/credentials", json={"web": {"client_id": "not desktop"}}).status_code == 422
    assert client.post("/api/sync/connect").status_code == 409


def test_legacy_import_rejects_bad_state_before_writing(client):
    assert client.post("/api/library/import", json={"words": [word()]}).json()["imported"] == 1
    before = app.DATA_FILE.read_bytes()
    response = client.post("/api/library/import", json={"words": [word("bad", srs={"d": "broken"})]})
    assert response.status_code == 422
    assert app.DATA_FILE.read_bytes() == before


def test_cache_lock_rejects_second_process_and_releases(tmp_path):
    path = tmp_path / "words.json"
    held = instance_lock.acquire(path)
    try:
        with pytest.raises(RuntimeError, match="另一个"):
            instance_lock.acquire(path)
    finally:
        held.close()
    instance_lock.acquire(path).close()











def test_future_cache_version_never_overwrites_existing_data(tmp_path):
    path = tmp_path / "words.json"
    data = storage.commit(path, {"words": [word()]})
    data["_sync"]["version"] = 999
    storage.atomic_write(path, data)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="版本"):
        storage.read(path)
    with pytest.raises(ValueError):
        storage.commit(path, {"words": []})
    assert path.read_bytes() == original
