"""间隔复习队列、统计与持久化回归测试。"""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

import app


def _word(word_id: str, text: str, created_at: str, **extra) -> dict:
    return {
        "id": word_id,
        "word": text,
        "phonetic": "",
        "definition": "n. 测试释义",
        "example": "This is a test.",
        "created_at": created_at,
        **extra,
    }


@pytest.fixture
def isolated_words(tmp_path, monkeypatch):
    """所有写入都落到 pytest 临时目录，绝不触碰真实 words.json。"""
    data_file = tmp_path / "words.json"
    monkeypatch.setattr(app, "DATA_FILE", data_file)
    return data_file


def test_stats_respect_persisted_daily_new_limit():
    now = datetime(2026, 8, 10, 12, 0, tzinfo=app.CHINA_TZ)
    words = [
        _word(
            "reviewed-today",
            "alpha",
            "2026-08-01T09:00:00+08:00",
            srs={
                "d": 5.0,
                "s": 10.0,
                "first_review_at": "2026-08-10T08:00:00+08:00",
                "last_review_at": "2026-08-10T08:00:00+08:00",
                "due_at": "2026-08-20T08:00:00+08:00",
                "reps": 1,
                "lapses": 0,
            },
        ),
        _word("new-1", "beta", "2026-08-02T09:00:00+08:00"),
        _word("new-2", "gamma", "2026-08-03T09:00:00+08:00"),
    ]

    stats = app._review_stats_for(words, now, daily_new_limit=2)

    assert stats["new_today"] == 1
    assert stats["new_remaining"] == 2
    assert stats["due_today"] == 1


def test_due_queue_prioritizes_overdue_reviews(isolated_words, monkeypatch):
    now = datetime.now(app.CHINA_TZ)
    data = {
        "words": [
            _word("new", "newest", (now - timedelta(days=2)).isoformat()),
            _word(
                "due",
                "overdue",
                (now - timedelta(days=20)).isoformat(),
                srs={
                    "d": 5.0,
                    "s": 3.0,
                    "first_review_at": (now - timedelta(days=10)).isoformat(),
                    "last_review_at": (now - timedelta(days=5)).isoformat(),
                    "due_at": (now - timedelta(days=2)).isoformat(),
                    "reps": 2,
                    "lapses": 0,
                },
            ),
        ]
    }
    app.save_words(data)
    monkeypatch.setattr(app.config, "get_srs_config", lambda: {"daily_new_limit": 20})

    result = app.review_due(limit=2)

    assert [card["id"] for card in result["cards"]] == ["due", "new"]
    assert result["cards"][0]["is_new"] is False
    assert result["cards"][1]["is_new"] is True
    assert set(result["cards"][0]["predicted_intervals"]) == {"1", "2", "3", "4"}


def test_review_rating_persists_and_counts_new_word_today(isolated_words):
    word = _word("target", "memory", "2026-08-01T09:00:00+08:00")
    app.save_words({"words": [word]})

    result = app.post_review("target", {"rating": 3})
    persisted = app.load_words()["words"][0]["srs"]

    assert persisted["reps"] == 1
    assert persisted["lapses"] == 0
    assert persisted["first_review_at"] == persisted["last_review_at"]
    assert app._parse_review_time(persisted["due_at"]) > app._parse_review_time(
        persisted["last_review_at"]
    )
    assert result["card"]["is_new"] is False
    assert result["next_interval_seconds"] > 0

    stats = app._review_stats_for(
        app.load_words()["words"], datetime.now(app.CHINA_TZ), daily_new_limit=20
    )
    assert stats["new_today"] == 1


def test_again_increments_lapses_on_repeated_review(isolated_words):
    app.save_words({
        "words": [_word("target", "forget", "2026-08-01T09:00:00+08:00")]
    })

    app.post_review("target", {"rating": 1})
    app.post_review("target", {"rating": 1})
    srs_state = app.load_words()["words"][0]["srs"]

    assert srs_state["reps"] == 2
    assert srs_state["lapses"] == 2


def test_review_rejects_invalid_rating_without_writing(isolated_words):
    original = {"words": [_word("target", "safe", "2026-08-01T09:00:00+08:00")]}
    app.save_words(original)

    with pytest.raises(HTTPException) as exc_info:
        app.post_review("target", {"rating": 5})

    assert exc_info.value.status_code == 422
    assert app.load_words() == original

    with pytest.raises(HTTPException) as float_exc_info:
        app.post_review("target", {"rating": 3.0})

    assert float_exc_info.value.status_code == 422
    assert app.load_words() == original


def test_corrupt_srs_state_is_skipped_in_stats():
    now = datetime(2026, 8, 10, 12, 0, tzinfo=app.CHINA_TZ)
    corrupt = _word(
        "broken",
        "broken",
        "2026-08-01T09:00:00+08:00",
        srs={
            "d": 5.0,
            "s": "not-a-number",
            "last_review_at": "2026-08-01T09:00:00+08:00",
            "due_at": "2026-08-02T09:00:00+08:00",
        },
    )

    stats = app._review_stats_for([corrupt], now, daily_new_limit=20)

    assert stats["due_today"] == 0
    assert stats["invalid_count"] == 1


def test_missing_definition_is_excluded_from_review():
    now = datetime(2026, 8, 10, 12, 0, tzinfo=app.CHINA_TZ)
    incomplete = _word("empty", "pending", now.isoformat(), definition="")

    stats = app._review_stats_for([incomplete], now, daily_new_limit=20)

    assert stats["total"] == 0
    assert stats["due_today"] == 0
