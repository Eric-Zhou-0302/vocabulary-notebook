"""New-word previews and date ordering use isolated data and mocked enrichment."""
import asyncio

import pytest
from fastapi.testclient import TestClient

import app


def word(word_id, created_at, **extra):
    return {"id": word_id, "word": word_id, "definition": "n. 测试", "phonetic": "",
            "example": "This is a test.", "created_at": created_at, **extra}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_FILE", tmp_path / "words.json")
    monkeypatch.setattr(app, "_enrich_states", {})
    monkeypatch.setattr(app, "_enriching_ids", {})
    monkeypatch.setattr(app, "_enrich_current", None)
    monkeypatch.setattr(app, "_enrich_batch_total", 0)
    monkeypatch.setattr(app, "_enrich_batch_done", 0)
    return app.DATA_FILE


def test_time_order_matches_pagination_and_json_csv_exports_without_rewriting(isolated):
    app.save_words({"words": [word("older", "2026-10-18T09:00:00+08:00", srs={"reps": 3}),
                              word("newest", "2026-10-18T03:00:00Z"),
                              word("middle", "2026-10-18T10:00:00")]})
    original = isolated.read_bytes()
    client = TestClient(app.app)
    result = client.get("/api/words", params={"sort": "created_desc", "size": 2}).json()
    assert [w["id"] for w in result["words"]] == ["newest", "middle"]
    result = client.get("/api/words", params={"sort": "created_desc", "size": 2, "page": 2}).json()
    assert [w["id"] for w in result["words"]] == ["older"]
    exported = client.get("/api/words/export", params={"sort": "created_desc"}).json()
    assert [w["id"] for w in exported["words"]] == ["newest", "middle", "older"]
    csv = client.get("/api/words/export", params={"sort": "created_desc", "format": "csv"}).text
    assert csv.index("newest") < csv.index("middle") < csv.index("older")
    result = client.get("/api/words", params={"sort": "created_asc", "q": "test"}).json()
    assert result["words"] == []
    result = client.get("/api/words", params={"sort": "created_asc"}).json()
    assert [w["id"] for w in result["words"]] == ["older", "middle", "newest"]
    assert isolated.read_bytes() == original


def test_legacy_invalid_dates_and_equal_instants_have_stable_order(isolated):
    data = {"words": [word("z", "2026-10-18T10:00:00+08:00"), word("a", "2026-10-18T02:00:00Z"),
                      word("invalid", "bad-date"), word("missing", None)]}
    assert [w["id"] for w in app._filter_words(data, "", "", "created_desc")] == ["z", "a", "missing", "invalid"]
    assert [w["id"] for w in app._filter_words(data, "", "", "alpha_asc")] == ["a", "invalid", "missing", "z"]
    assert app._filter_words(data, "", "") == data["words"]


@pytest.mark.parametrize("outcome", ["success", "empty", "rejected"])
def test_preview_status_and_persisted_result_survive_missed_sse(isolated, monkeypatch, outcome):
    async def enrich(_word):
        if outcome == "empty":
            return "", "", ""
        return "/test/", "n. 合同", "The contract is valid."

    monkeypatch.setattr(app, "enrich_word", enrich)
    monkeypatch.setattr(app, "_enrich_post_check", lambda *args: (outcome != "rejected", "测试校验失败"))

    async def scenario():
        monkeypatch.setattr(app, "_enrich_queue", asyncio.Queue())
        monkeypatch.setattr(app, "_event_queue", asyncio.Queue())
        created = await app.create_word({"word": "contract"})
        word_id = created["word"]["id"]
        assert created["enrichment"]["status"] == "queued"
        worker = asyncio.create_task(app._enrich_worker())
        try:
            await asyncio.wait_for(app._enrich_queue.join(), timeout=2)
            result = app.get_word(word_id)  # No SSE consumer is required for the preview.
            if outcome == "success":
                assert result["enrichment"]["status"] == "ready"
                assert result["word"]["definition"] == "n. 合同"
                assert result["word"]["example"] == "The contract is valid."
            else:
                assert result["enrichment"]["status"] == "failed"
                assert result["enrichment"]["error"]
                assert result["word"]["definition"] == ""
            assert "enrichment" not in app.load_words()["words"][0]
        finally:
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker

    asyncio.run(scenario())


def test_manual_definition_is_immediately_available_and_existing_words_stay_compatible(isolated):
    app.save_words({"words": [word("manual", "2026-10-18T10:00:00+08:00"),
                              word("legacy", "2026-10-18T09:00:00+08:00", definition="")]})
    assert app.get_word("manual")["enrichment"]["status"] == "ready"
    assert app.get_word("legacy")["enrichment"]["status"] == "idle"
