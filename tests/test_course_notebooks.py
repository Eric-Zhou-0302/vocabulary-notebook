import asyncio
import json
import httpx
import pytest
from tests.local_client import TestClient
import app
import sync_storage

def test_course_move_and_review_replicate_to_second_cache(client, tmp_path):
    book = client.post('/api/notebooks', json={'name': 'Law', 'description': 'Contract law'}).json()['notebook']['id']
    word = client.post('/api/words', json={'word': 'covenant', 'definition': 'n. 契约'}).json()['word']['id']
    assert client.put('/api/words/' + word, json={'notebook_id': book}).status_code == 200
    assert client.post('/api/words/' + word + '/review', json={'rating': 3}).status_code == 200
    local = sync_storage.read(app.DATA_FILE)
    operations = list(local['_sync']['operations'].values())
    remote = tmp_path / 'second-device.json'
    assert sync_storage.merge(remote, operations) > 0
    restored = sync_storage.read(remote)
    assert restored['notebooks'] == local['notebooks']
    assert restored['words'] == local['words']
    assert restored['words'][0]['notebook_id'] == book
    assert restored['words'][0]['srs']['reps'] == 1
    assert sync_storage.merge(remote, operations) == 0

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_FILE", tmp_path/"words.json")
    monkeypatch.setattr(app.config, "_CONFIG", {"provider":"ollama", "ollama":{"url":"http://127.0.0.1:11434/api/generate", "model":"test"}})
    return TestClient(app.app)

def test_notebooks_isolate_duplicate_words_reviews_and_exports(client):
    law = client.post("/api/notebooks", json={"name": "法律", "description": "合同法课程"}).json()["notebook"]["id"]
    finance = client.post("/api/notebooks", json={"name": "金融"}).json()["notebook"]["id"]
    first = client.post("/api/words", json={"word": "security", "definition": "n. 担保", "notebook_id": law})
    second = client.post("/api/words", json={"word": "security", "definition": "n. 证券", "notebook_id": finance})
    assert first.status_code == second.status_code == 200
    assert client.post("/api/words", json={"word": "SECURITY", "notebook_id": law}).status_code == 409
    assert client.get("/api/words", params={"notebook_id": law}).json()["total"] == 1
    assert client.get("/api/review/due", params={"notebook_id": finance}).json()["cards"][0]["definition"] == "n. 证券"
    word_id = first.json()["word"]["id"]
    assert client.post(f"/api/words/{word_id}/review", json={"rating": 3}).status_code == 200
    assert client.get("/api/review/stats", params={"notebook_id": law}).json()["new_today"] == 1
    assert client.get("/api/review/stats", params={"notebook_id": finance}).json()["new_today"] == 0
    exported = client.get("/api/words/export", params={"notebook_id": law}).json()
    assert len(exported["words"]) == 1 and exported["words"][0]["srs"]["reps"] == 1
    assert "_sync" not in exported


def test_ollama_request_stays_local_and_includes_course_context(monkeypatch):
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"response": json.dumps({"phonetic": "/test/", "definition": "n. 对价", "example": "Consideration is required."})})
    real_client = httpx.AsyncClient
    def local_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(app.httpx, "AsyncClient", local_client)
    monkeypatch.setattr(app.config, "get_provider", lambda: "ollama")
    monkeypatch.setattr(app.config, "get_ollama_config", lambda: {"url": "http://127.0.0.1:11434/api/generate", "model": "test"})
    result = asyncio.run(app.enrich_word("consideration", "法律：合同法"))
    assert result[1] == "n. 对价"
    assert len(seen) == 1 and seen[0].url.host == "127.0.0.1"
    assert "法律：合同法" in json.loads(seen[0].content)["prompt"]


def test_deepseek_provider_and_course_context_remain_supported(monkeypatch):
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"phonetic": "/test/", "definition": "n. 证券", "example": "The security pays interest."})}}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(app.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(app.config, "get_provider", lambda: "deepseek")
    monkeypatch.setattr(app.config, "get_deepseek_config", lambda: {"api_key": "test-only", "model": "existing-model"})
    assert asyncio.run(app.enrich_word("security", "金融课程"))[1] == "n. 证券"
    assert str(seen[0].url) == "https://api.deepseek.com/chat/completions"
    assert "金融课程" in json.loads(seen[0].content)["messages"][0]["content"]


def test_legacy_read_and_first_edit_preserve_original_backup(client):
    original = {"words":[{"id":"legacy", "word":"Contract", "definition":"n. 合同", "phonetic":"", "example":"", "created_at":"2026-10-18T00:00:00Z", "srs":{"reps":3}}]}
    app.DATA_FILE.write_text(json.dumps(original), encoding="utf8")
    before=app.DATA_FILE.read_bytes()
    assert client.get("/api/notebooks").json()["notebooks"][0]["word_count"] == 1
    assert app.DATA_FILE.with_suffix(".json.legacy.bak").read_bytes() == before
    law=client.post("/api/notebooks",json={"name":"Law"}).json()["notebook"]["id"]
    assert app.DATA_FILE.with_suffix(".json.legacy.bak").read_bytes() == before
    assert client.put("/api/words/legacy",json={"notebook_id":law}).status_code == 200
    assert client.get("/api/words/legacy").json()["word"]["srs"] == {"reps":3}

def test_move_conflict_does_not_overwrite_either_record(client):
    law=client.post("/api/notebooks",json={"name":"Law"}).json()["notebook"]["id"]
    a=client.post("/api/words",json={"word":"bond","definition":"n. 担保"}).json()["word"]
    client.post("/api/words",json={"word":"bond","definition":"n. 债券","notebook_id":law})
    before=app.DATA_FILE.read_bytes()
    assert client.put('/api/words/'+a['id'],json={"notebook_id":law}).status_code == 409
    assert app.DATA_FILE.read_bytes() == before
