# SRS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace random-order Flashcard with FSRS-powered spaced repetition. New words have `srs: null`, reviewed words track `d`/`s`/`last_review_at`/`reps`/`lapses`. App nav shows "· N" due-today badge.

**Architecture:** Backend adds `fsrs.py` (self-implemented algorithm) + 3 endpoints (`/api/review/due`, `/api/words/{id}/review`, `/api/review/stats`). Frontend replaces `Flashcard.jsx` with `SpacedReview.jsx` (4 buttons, 1-4 keyboard, predicted-interval preview), adds `useDueCount` hook for nav badge, lazy-migrates existing 191 words (missing `srs` field = new).

**Tech Stack:** Python 3.9 (existing venv at `.venv`), FastAPI, React + Vite, FSRS-4.5 algorithm (community default weights, ~120 lines self-implemented). No new third-party deps except `pytest` (dev only).

**Reference spec:** `docs/superpowers/specs/2026-06-14-srs-design.md` (commit `b0b6afc`).

---

## File Structure

**Backend (Python):**
- `fsrs.py` — new, FSRS algorithm module (~120 lines, zero deps)
- `tests/test_fsrs.py` — new, pytest tests for algorithm
- `app.py` — modify: add `_daily` state, 3 new endpoints, srs helpers
- `requirements-dev.txt` — new, lists pytest (dev only)
- `words.json` — gets new `srs` field on first review (lazy migration)

**Frontend (React):**
- `frontend/src/components/SpacedReview.jsx` — new, replaces Flashcard
- `frontend/src/components/Flashcard.jsx` — delete
- `frontend/src/pages/Review.jsx` — modify: rename tab, add stats header, swap component
- `frontend/src/useDueCount.js` — new, 60s polling hook
- `frontend/src/App.jsx` — modify: add nav badge
- `frontend/src/App.css` — modify: add `--warn` / `--info` color tokens + SpacedReview styles

---

## Task 1: Install pytest as dev dependency

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create requirements-dev.txt**

```text
pytest>=7.0
```

Write to `/Users/eric_zhou/Projects/vocabulary-notebook/requirements-dev.txt`.

- [ ] **Step 2: Install pytest in project venv**

Run: `/Users/eric_zhou/Projects/vocabulary-notebook/.venv/bin/pip install -r /Users/eric_zhou/Projects/vocabulary-notebook/requirements-dev.txt`
Expected: `Successfully installed pytest-X.X.X ...`

- [ ] **Step 3: Verify pytest is callable**

Run: `/Users/eric_zhou/Projects/vocabulary-notebook/.venv/bin/pytest --version`
Expected: `pytest X.X.X`

- [ ] **Step 4: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add requirements-dev.txt
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "chore: add pytest dev dep"
```

---

## Task 2: Write failing tests for FSRS algorithm

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_fsrs.py`

- [ ] **Step 1: Create tests/__init__.py**

Write empty file: `/Users/eric_zhou/Projects/vocabulary-notebook/tests/__init__.py`

- [ ] **Step 2: Write property tests**

```python
"""FSRS 算法属性 + 边界测试。"""
import math
import pytest
from fsrs import (
    retrievability,
    initial_stability,
    initial_difficulty,
    next_difficulty,
    next_recall_stability,
    next_forget_stability,
    next_interval,
)


# ── Retrievability ─────────────────────────────────────

def test_retrievability_at_zero_elapsed_is_one():
    """刚学完 (elapsed=0) 回忆概率应为 1.0。"""
    assert retrievability(elapsed_days=0, stability=10) == pytest.approx(1.0, abs=1e-9)


def test_retrievability_monotonically_decreases_in_time():
    """时间越长，回忆概率越低。"""
    r0 = retrievability(0, 10)
    r5 = retrievability(5, 10)
    r20 = retrievability(20, 10)
    assert r0 > r5 > r20
    assert r20 > 0  # 不应归零


def test_retrievability_monotonically_increases_in_stability():
    """稳定性越高，回忆概率越高（同等 elapsed）。"""
    r_low = retrievability(10, 5)
    r_high = retrievability(10, 50)
    assert r_low < r_high


# ── Initial values for new cards ───────────────────────

def test_initial_stability_good_again_has_ordering():
    """新词 Good 评分的初始稳定性 > Hard > Again。"""
    s_again = initial_stability(1)
    s_hard = initial_stability(2)
    s_good = initial_stability(3)
    s_easy = initial_stability(4)
    assert s_again < s_hard < s_good < s_easy


def test_initial_difficulty_clamped_to_range():
    """初始难度应在 [1, 10] 范围内。"""
    for r in (1, 2, 3, 4):
        d = initial_difficulty(r)
        assert 1.0 <= d <= 10.0


# ── Difficulty updates ─────────────────────────────────

def test_next_difficulty_again_increases_difficulty():
    """Again 评分应增加难度（更难记住）。"""
    d = 5.0
    new_d = next_difficulty(d, rating=1)
    assert new_d > d


def test_next_difficulty_easy_decreases_difficulty():
    """Easy 评分应降低难度（更好记住）。"""
    d = 5.0
    new_d = next_difficulty(d, rating=4)
    assert new_d < d


# ── Stability updates ──────────────────────────────────

def test_again_decreases_stability():
    """Again 后稳定性应下降。"""
    s = 10.0
    d = 5.0
    r = retrievability(5, s)  # 0.66
    new_s = next_forget_stability(d, s, r)
    assert new_s < s


def test_good_increases_stability():
    """Good 后稳定性应上升。"""
    s = 10.0
    d = 5.0
    r = retrievability(5, s)
    new_s = next_recall_stability(d, s, r, rating=3)
    assert new_s > s


def test_easy_increases_stability_more_than_good():
    """Easy 应比 Good 让稳定性涨得更多。"""
    s, d = 10.0, 5.0
    r = retrievability(5, s)
    s_good = next_recall_stability(d, s, r, rating=3)
    s_easy = next_recall_stability(d, s, r, rating=4)
    assert s_easy > s_good


# ── Interval ───────────────────────────────────────────

def test_next_interval_zero_at_zero_stability():
    """stability=0 时 interval 应为 0（或极小）。"""
    assert next_interval(0) == 0


def test_next_interval_grows_with_stability():
    """稳定性越高，下次复习间隔越长。"""
    i_low = next_interval(5)
    i_high = next_interval(50)
    assert i_low < i_high
```

Write to `/Users/eric_zhou/Projects/vocabulary-notebook/tests/test_fsrs.py`.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/eric_zhou/Projects/vocabulary-notebook && /Users/eric_zhou/Projects/vocabulary-notebook/.venv/bin/pytest tests/test_fsrs.py -v`
Expected: `ModuleNotFoundError: No module named 'fsrs'`

- [ ] **Step 4: Commit failing tests**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add tests/__init__.py tests/test_fsrs.py
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "test(fsrs): add property tests for FSRS algorithm"
```

---

## Task 3: Implement FSRS algorithm module

**Files:**
- Create: `fsrs.py`

- [ ] **Step 1: Write fsrs.py**

```python
"""FSRS-4.5 算法 — 间隔重复调度。

参考 open-spaced-repetition/fsrs4anki（社区训练好的默认权重）。
不存 review log（v1 不调参，只用默认权重）。

Rating 含义（与 Anki 一致）：
  1 = Again（重来/忘了）
  2 = Hard（困难）
  3 = Good（良好/记得）
  4 = Easy（简单）
"""
import math
from typing import Tuple

# FSRS-4.5 社区默认权重（17 个）
W = (
    0.4072, 1.1829, 3.1262, 7.2102, 5.0679,  # 0-4: initial S(1..4), 4=initial D offset
    1.5321, 0.1192, 0.6573, 1.2480,           # 5-8: initial D slope, D update, S update (recall)
    0.1716, 0.6234, 1.6463, 0.1341,           # 9-12: recall stability power, S(1-r) W[10], S+1 pow, S(1-r) fail
    0.3496, 1.4729, 0.2573, 2.8085,           # 13-16: forget power, fail exp, hard slope, easy bonus
)

# 遗忘曲线参数
DECAY = -0.5
FACTOR = 19 / 81  # ≈ 0.2346
REQUEST_RETENTION = 0.9  # 期望回忆概率 90%


def retrievability(elapsed_days: float, stability: float) -> float:
    """给定稳定性和经过天数，返回当前可回忆概率 R ∈ (0, 1]。"""
    if stability <= 0:
        return 1.0
    return (1.0 + FACTOR * elapsed_days / stability) ** DECAY


def initial_stability(rating: int) -> float:
    """新词第一次复习后的初始稳定性 S。"""
    return max(W[rating - 1], 0.1)


def initial_difficulty(rating: int) -> float:
    """新词第一次复习后的初始难度 D，clamp 到 [1, 10]。"""
    d = W[4] - math.exp(W[5] * (rating - 1)) + 1
    return min(max(d, 1.0), 10.0)


def next_difficulty(d: float, rating: int) -> float:
    """复习后更新难度 D。Again 增加，Easy 降低。"""
    new_d = d - W[6] * (rating - 3)
    return min(max(new_d, 1.0), 10.0)


def next_recall_stability(d: float, s: float, r: float, rating: int) -> float:
    """成功回忆后（Hard/Good/Easy）的稳定性 S'。"""
    if rating == 2:  # Hard：稳定性微增（甚至略降）
        # Hard 几乎不增加稳定性；公式：S · (1 + W[15] · (rating-3) · exp(W[16]·(1-R)))
        # (rating-3) = -1，所以是减少
        new_s = s * (1.0 + W[15] * (rating - 3) * math.exp(W[16] * (1.0 - r)))
    elif rating == 3:  # Good：标准间隔
        new_s = s * (
            1.0
            + (math.exp(W[8]) - 1.0)
            * (11.0 - d)
            * s ** (-W[9])
            * (math.exp((1.0 - r) * W[10]) - 1.0)
        )
    elif rating == 4:  # Easy：额外奖励
        new_s = s * (
            1.0
            + (math.exp(W[8]) - 1.0)
            * (11.0 - d)
            * s ** (-W[9])
            * (math.exp((1.0 - r) * W[10]) - 1.0)
            * W[16]
        )
    else:
        raise ValueError(f"rating must be 2/3/4 for recall, got {rating}")
    return max(new_s, 0.1)


def next_forget_stability(d: float, s: float, r: float) -> float:
    """失败（Again=1）后的稳定性 S'。"""
    new_s = (
        W[11]
        * d ** (-W[12])
        * ((s + 1.0) ** W[13] - 1.0)
        * math.exp((1.0 - r) * W[14])
    )
    return max(new_s, 0.1)


def update(d: float, s: float, rating: int, elapsed_days: float) -> Tuple[float, float]:
    """复习后返回 (新 D, 新 S)。"""
    new_d = next_difficulty(d, rating)
    r = retrievability(elapsed_days, s)
    if rating == 1:  # Again
        new_s = next_forget_stability(d, s, r)
    else:
        new_s = next_recall_stability(d, s, r, rating)
    return new_d, new_s


def next_interval_days(s: float, request_retention: float = REQUEST_RETENTION) -> float:
    """根据稳定性和目标回忆率，计算下次复习间隔（天）。"""
    if s <= 0:
        return 0.0
    return s / FACTOR * (request_retention ** (1.0 / DECAY) - 1.0)


def format_interval(seconds: float) -> str:
    """把秒数格式化成可读字符串：30s / 5m / 3h / 5d / 2mo / 1y。"""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    days = seconds / 86400
    if days < 30:
        return f"{int(round(days))}d"
    if days < 365:
        return f"{int(round(days / 30))}mo"
    return f"{round(days / 365, 1)}y"
```

Write to `/Users/eric_zhou/Projects/vocabulary-notebook/fsrs.py`.

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /Users/eric_zhou/Projects/vocabulary-notebook && /Users/eric_zhou/Projects/vocabulary-notebook/.venv/bin/pytest tests/test_fsrs.py -v`
Expected: All ~12 tests pass.

- [ ] **Step 3: If any test fails, debug the FSRS formulas**

Specifically check:
- `retrievability` — must equal 1.0 at elapsed=0 (the math: `(1 + 0)^(-0.5) = 1`)
- `next_difficulty` — for rating=3 (Good), `(rating-3) = 0` so `new_d = d`. Only Again/Easy change.
- `next_recall_stability` — for rating=3, formula should produce `new_s > s`

Adjust the formulas in `fsrs.py` if any test fails. Re-run until green.

- [ ] **Step 4: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add fsrs.py
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(fsrs): implement FSRS-4.5 algorithm with 17 default weights"
```

---

## Task 4: Add `_daily` state + srs helpers to app.py

**Files:**
- Modify: `app.py:71-78` (add `_daily` global)

- [ ] **Step 1: Add `_daily` global after existing `_enrich_*` declarations**

Find this block in `app.py`:
```python
# 进度追踪
_enrich_current: Optional[str] = None
_enrich_batch_total: int = 0
_enrich_batch_done: int = 0
```

Add immediately after:
```python
# ─── SRS 每日统计 ────────────────────────────────────────
_daily: dict = {
    "date": "",       # YYYY-MM-DD (Beijing)，跨日自动重置
    "new_today": 0,   # 今日新词复习数（srs was null → 已评）
    "review_today": 0,
}
DAILY_NEW_LIMIT = 20  # 每日新词上限，可后续挪到 config
```

- [ ] **Step 2: Add `import fsrs` and helper functions near the top (after other globals)**

Add immediately after the new `_daily` block:
```python
import fsrs  # noqa: E402
```

- [ ] **Step 3: Add `_reset_daily_if_new_day` and srs helper functions**

Add after `_enqueue_enrich_batch` and `_maybe_reset_batch_if_idle` (around line 442):
```python
# ─── SRS 辅助 ─────────────────────────────────────────

def _today_iso() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y-%m-%d")


def _reset_daily_if_new_day() -> None:
    """跨日重置 _daily 计数器。"""
    today = _today_iso()
    if _daily["date"] != today:
        _daily["date"] = today
        _daily["new_today"] = 0
        _daily["review_today"] = 0


def _word_due_at(word: dict) -> str:
    """返回单词的 next_due_at ISO 字符串。新词 = '1970'（立即到期）。"""
    srs = word.get("srs")
    if not srs:
        return "1970-01-01T00:00:00+08:00"
    last = datetime.fromisoformat(srs["last_review_at"])
    interval = fsrs.next_interval_days(srs["s"])
    return (last + timedelta(days=interval)).isoformat()


def _predicted_intervals(srs: dict | None) -> dict:
    """返回 {rating_int: 格式化字符串} 预览。"""
    from fsrs import format_interval
    if not srs:
        # 新词：没有 D/S，preview 用经验默认（与初始 S 对应）
        return {
            "1": "1m",   # Again：1 分钟后重学
            "2": "1d",
            "3": "5d",
            "4": "10d",
        }
    last = datetime.fromisoformat(srs["last_review_at"])
    now = datetime.now(CHINA_TZ)
    elapsed_days = max((now - last).total_seconds() / 86400, 0)
    d, s = srs["d"], srs["s"]
    r = fsrs.retrievability(elapsed_days, s)
    out = {}
    for rating in (1, 2, 3, 4):
        if rating == 1:
            new_s = fsrs.next_forget_stability(d, s, r)
        else:
            new_s = fsrs.next_recall_stability(d, s, r, rating)
        interval_days = fsrs.next_interval_days(new_s)
        out[str(rating)] = format_interval(interval_days * 86400)
    return out
```

- [ ] **Step 4: Verify Python imports cleanly**

Run: `cd /Users/eric_zhou/Projects/vocabulary-notebook && /Users/eric_zhou/Projects/vocabulary-notebook/.venv/bin/python -c "import app; print('imports OK')"`
Expected: `imports OK`

- [ ] **Step 5: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add app.py
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): add _daily state and srs helper functions"
```

---

## Task 5: Implement `GET /api/review/stats` endpoint

**Files:**
- Modify: `app.py` (add endpoint before `enrich-missing`)

- [ ] **Step 1: Add stats endpoint**

Add this endpoint **after** `_maybe_reset_batch_if_idle` definition and **before** `enrich-missing`:
```python
@app.get("/api/review/stats")
def review_stats():
    """轻量端点：复习统计。App nav 角标用。"""
    _reset_daily_if_new_day()
    data = load_words()
    words = [w for w in data["words"] if w.get("definition", "").strip()]
    new_remaining = sum(1 for w in words if not w.get("srs"))
    now = datetime.now(CHINA_TZ)
    review_due = 0
    for w in words:
        srs = w.get("srs")
        if not srs:
            continue
        last = datetime.fromisoformat(srs["last_review_at"])
        interval = fsrs.next_interval_days(srs["s"])
        if now >= last + timedelta(days=interval):
            review_due += 1
    new_due_today = max(0, DAILY_NEW_LIMIT - _daily["new_today"])
    due_today = min(new_remaining, new_due_today) + review_due
    return {
        "total": len(words),
        "due_today": due_today,
        "new_remaining": new_remaining,
        "review_due": review_due,
        "new_today": _daily["new_today"],
        "review_today": _daily["review_today"],
    }
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add app.py
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): add GET /api/review/stats endpoint"
```

---

## Task 6: Implement `GET /api/review/due` endpoint

**Files:**
- Modify: `app.py` (add endpoint)

- [ ] **Step 1: Add due endpoint**

Add after `review_stats`:
```python
@app.get("/api/review/due")
def review_due(new_limit: int = Query(default=20, ge=0, le=100),
               limit: int = Query(default=20, ge=1, le=100)):
    """下一批 due 卡片（新词 + 复习词混合）。"""
    _reset_daily_if_new_day()
    data = load_words()
    words = [w for w in data["words"] if w.get("definition", "").strip()]

    now = datetime.now(CHINA_TZ)
    new_words = [w for w in words if not w.get("srs")]
    new_words.sort(key=lambda w: w["created_at"])  # 最老的先

    review_words = []
    for w in words:
        srs = w.get("srs")
        if not srs:
            continue
        last = datetime.fromisoformat(srs["last_review_at"])
        interval = fsrs.next_interval_days(srs["s"])
        due_at = last + timedelta(days=interval)
        if now >= due_at:
            w["_due_at"] = due_at
            review_words.append(w)
    review_words.sort(key=lambda w: w["_due_at"])  # 最过期的先

    # 队列前 N 是新词（受 new_limit 约束）
    new_due_today = max(0, DAILY_NEW_LIMIT - _daily["new_today"])
    new_quota = min(len(new_words), new_due_today, limit)
    new_take = new_words[:new_quota]
    review_quota = max(0, limit - len(new_take))
    review_take = review_words[:review_quota]

    # 拼装 cards（去掉临时字段）
    cards = []
    for w in new_take + review_take:
        card = {k: v for k, v in w.items() if not k.startswith("_")}
        card["predicted_intervals"] = _predicted_intervals(w.get("srs"))
        cards.append(card)

    stats_resp = {
        "total": len(words),
        "due_today": min(len(new_words), new_due_today) + sum(
            1 for w in words if w.get("srs") and now >= datetime.fromisoformat(w["srs"]["last_review_at"]) + timedelta(days=fsrs.next_interval_days(w["srs"]["s"]))
        ),
        "new_remaining": len(new_words),
        "review_due": len(review_words),
        "new_today": _daily["new_today"],
        "review_today": _daily["review_today"],
    }
    return {"cards": cards, "stats": stats_resp}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add app.py
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): add GET /api/review/due with new+review queue mix"
```

---

## Task 7: Implement `POST /api/words/{word_id}/review` endpoint

**Files:**
- Modify: `app.py` (add endpoint — must be before `/api/words/{word_id}`)

- [ ] **Step 1: Add review endpoint BEFORE the existing `get_word` route**

Find the line `@app.get("/api/words/{word_id}")` and insert **before** it:
```python
@app.post("/api/words/{word_id}/review")
def post_review(word_id: str, body: dict):
    """记录一次复习，调 FSRS 更新 SRS 状态。"""
    _reset_daily_if_new_day()
    rating = body.get("rating")
    if rating not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="rating 必须是 1/2/3/4")

    with _write_lock:
        data = load_words()
        word = next((w for w in data["words"] if w["id"] == word_id), None)
        if not word:
            raise HTTPException(status_code=404, detail="单词不存在")

        was_new = word.get("srs") is None
        now = datetime.now(CHINA_TZ)

        if was_new:
            # 新词：初始化 D, S
            d = fsrs.initial_difficulty(rating)
            s = fsrs.initial_stability(rating)
        else:
            srs = word["srs"]
            last = datetime.fromisoformat(srs["last_review_at"])
            elapsed_days = max((now - last).total_seconds() / 86400, 0)
            d, s = fsrs.update(srs["d"], srs["s"], rating, elapsed_days)

        word["srs"] = {
            "d": d,
            "s": s,
            "last_review_at": now.isoformat(),
            "reps": (word.get("srs", {}) or {}).get("reps", 0) + 1,
            "lapses": (word.get("srs", {}) or {}).get("lapses", 0) + (1 if rating == 1 else 0),
        }
        save_words(data)

    # 累加每日统计
    if was_new:
        _daily["new_today"] += 1
    else:
        _daily["review_today"] += 1

    interval_seconds = fsrs.next_interval_days(s) * 86400
    return {
        "word": word,
        "next_interval_seconds": interval_seconds,
    }
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add app.py
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): add POST /api/words/{id}/review with FSRS update"
```

---

## Task 8: Smoke test all 3 endpoints with curl

**Files:** none (verification only)

- [ ] **Step 1: Start backend**

Run: `pkill -9 -f "Python app.py" 2>/dev/null; sleep 1; cd /Users/eric_zhou/Projects/vocabulary-notebook && /Users/eric_zhou/Projects/vocabulary-notebook/.venv/bin/python app.py &`
Expected: backend running on port 1400 (wait 3s before next step)

- [ ] **Step 2: Test /api/review/stats**

Run: `curl -s http://localhost:1400/api/review/stats | python3 -m json.tool`
Expected: JSON with `total > 0`, `due_today`, `new_remaining`, `review_due`, `new_today: 0`, `review_today: 0`.

- [ ] **Step 3: Test /api/review/due**

Run: `curl -s "http://localhost:1400/api/review/due?new_limit=2&limit=3" | python3 -m json.tool`
Expected: 3 cards in `cards` array, each with `id`, `word`, `definition`, `srs` (null for new), `predicted_intervals: {1,2,3,4}`.

- [ ] **Step 4: Test POST /api/words/{id}/review**

Pick a word id from step 3's output. Then:
Run: `curl -s -X POST http://localhost:1400/api/words/<WORD_ID>/review -H "Content-Type: application/json" -d '{"rating": 3}' | python3 -m json.tool`
Expected: `word.srs` no longer null, has `d`/`s`/`last_review_at`/`reps: 1`/`lapses: 0`. `next_interval_seconds > 0`.

- [ ] **Step 5: Test rating=1 (Again) creates lapses**

Use a different word id. Run: `curl -s -X POST http://localhost:1400/api/words/<WORD_ID>/review -H "Content-Type: application/json" -d '{"rating": 1}' | python3 -c "import json,sys; d=json.load(sys.stdin); print('lapses:', d['word']['srs']['lapses'])"`
Expected: `lapses: 1`

- [ ] **Step 6: Verify daily counter incremented**

Run: `curl -s http://localhost:1400/api/review/stats | python3 -c "import json,sys; d=json.load(sys.stdin); print('new_today:', d['new_today'], 'review_today:', d['review_today'])"`
Expected: counters match the reviews done in steps 4 and 5 (2 new reviews).

- [ ] **Step 7: Test invalid rating**

Run: `curl -s -X POST http://localhost:1400/api/words/<WORD_ID>/review -H "Content-Type: application/json" -d '{"rating": 5}'`
Expected: HTTP 422 (rating must be 1-4)

- [ ] **Step 8: Kill backend**

Run: `pkill -9 -f "Python app.py"`

---

## Task 9: Add new color tokens to App.css

**Files:**
- Modify: `frontend/src/App.css` (add `--warn` and `--info` to both themes)

- [ ] **Step 1: Add `--warn` and `--info` to dark theme**

Find the `[data-theme="dark"]` block (around line 4-28). Add inside:
```css
  --warn: #d68a3a;   /* 暖橙，Hard 评分 */
  --info: #5a85b8;   /* 冷蓝，Easy 评分 */
```

(Place after the `--error` line.)

- [ ] **Step 2: Add same tokens to light theme**

Find the `[data-theme="light"]` block. Add inside:
```css
  --warn: #c97a2a;
  --info: #4a6f9a;
```

(Place after the `--error` line.)

- [ ] **Step 3: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add frontend/src/App.css
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "style: add --warn and --info color tokens for SRS rating buttons"
```

---

## Task 10: Create `useDueCount` hook

**Files:**
- Create: `frontend/src/useDueCount.js`

- [ ] **Step 1: Write the hook**

```javascript
import { useState, useEffect } from 'react'

/**
 * 轮询 /api/review/stats，返回今日 due 总数。
 * 用于 App nav 角标。
 */
export function useDueCount(intervalMs = 60000) {
  const [dueToday, setDueToday] = useState(0)

  useEffect(() => {
    let timer = null
    let aborted = false

    async function fetch() {
      try {
        const res = await fetch('/api/review/stats')
        if (res.ok && !aborted) {
          const data = await res.json()
          setDueToday(data.due_today || 0)
        }
      } catch {
        // 忽略网络错误
      }
    }

    fetch()
    timer = setInterval(fetch, intervalMs)
    return () => {
      aborted = true
      if (timer) clearInterval(timer)
    }
  }, [intervalMs])

  return dueToday
}
```

Write to `/Users/eric_zhou/Projects/vocabulary-notebook/frontend/src/useDueCount.js`.

- [ ] **Step 2: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add frontend/src/useDueCount.js
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): add useDueCount hook for nav badge"
```

---

## Task 11: Create `SpacedReview.jsx` component

**Files:**
- Create: `frontend/src/components/SpacedReview.jsx`

- [ ] **Step 1: Write the component**

```jsx
import { useState, useEffect, useCallback } from 'react'

const RATING_LABELS = {
  1: '重来',
  2: '困难',
  3: '良好',
  4: '简单',
}

const RATING_CLASS = {
  1: 'rating-again',
  2: 'rating-hard',
  3: 'rating-good',
  4: 'rating-easy',
}

/**
 * FSRS 间隔复习组件
 * 接收从 /api/review/due 拉来的 cards 队列，按 4 档评分推进。
 * Again 在队列末尾重新插入一次（同 session 重学）。
 */
export default function SpacedReview({ cards, onRate, onSessionEnd }) {
  const [queue, setQueue] = useState([])
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState(false)
  const [reviewedCount, setReviewedCount] = useState(0)
  const [newCount, setNewCount] = useState(0)
  const [reviewCount, setReviewCount] = useState(0)

  useEffect(() => {
    setQueue(cards)
    setIndex(0)
    setFlipped(false)
    setDone(false)
    setReviewedCount(0)
    setNewCount(cards.filter(c => !c.srs).length)
    setReviewCount(cards.filter(c => c.srs).length)
  }, [cards])

  const current = queue[index]

  const handleRate = useCallback(async (rating) => {
    if (!current || !flipped) return
    const isNew = !current.srs
    setReviewedCount(c => c + 1)
    if (isNew) setNewCount(c => c - 1)
    else setReviewCount(c => c - 1)

    try {
      await onRate(current.id, rating)
    } catch {
      // 失败不前进：弹 toast 由父组件处理
      return
    }

    if (rating === 1 && isNew) {
      // Again：队尾再插一次
      setQueue(prev => [...prev, current])
    }

    if (index + 1 >= queue.length) {
      setDone(true)
    } else {
      setIndex(i => i + 1)
      setFlipped(false)
    }
  }, [current, flipped, index, queue, onRate])

  const handleKey = useCallback((e) => {
    if (!current) return
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      if (!flipped) setFlipped(true)
      return
    }
    if (flipped && ['1', '2', '3', '4'].includes(e.key)) {
      e.preventDefault()
      handleRate(parseInt(e.key, 10))
    }
  }, [current, flipped, handleRate])

  useEffect(() => {
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleKey])

  if (done) {
    return (
      <div className="srs-done">
        <h2>本轮完成</h2>
        <p>共复习 <b>{reviewedCount}</b> 个（新词 {newCount > 0 ? '+' : ''}{reviewedCount - newCount} · 复习 {reviewedCount - (newCount < 0 ? 0 : newCount)}）</p>
        {queue.length > 0 && index + 1 >= queue.length && reviewedCount > 0 && (
          <p className="srs-done-hint">还有 {newCount + reviewCount} 个待复习</p>
        )}
        <button className="btn btn-primary" onClick={onSessionEnd} style={{ marginTop: 16 }}>
          再来一批
        </button>
      </div>
    )
  }

  if (!current) {
    return <div className="empty-state"><p>没有待复习的单词</p></div>
  }

  return (
    <div className="srs-container">
      <div className="srs-progress">
        第 {index + 1} / {queue.length} 个 · 空格翻面 · 1-4 评分
      </div>

      <div className="flashcard" onClick={() => !flipped && setFlipped(true)}>
        <div className={`flashcard-inner ${flipped ? 'flipped' : ''}`}>
          <div className="flashcard-front">
            <span className="word-display">{current.word}</span>
            {current.phonetic && <span className="phonetic-display">{current.phonetic}</span>}
          </div>
          <div className="flashcard-back">
            <span className="word-display">{current.word}</span>
            {current.phonetic && <span className="phonetic-display">{current.phonetic}</span>}
            <span className="definition-display">{current.definition}</span>
            {current.example && <span className="example-display">"{current.example}"</span>}
          </div>
        </div>
      </div>

      {flipped && (
        <div className="srs-rating-grid">
          {[1, 2, 3, 4].map(r => (
            <button
              key={r}
              type="button"
              className={`srs-rating-btn ${RATING_CLASS[r]}`}
              onClick={() => handleRate(r)}
            >
              <span className="rating-label">{r} · {RATING_LABELS[r]}</span>
              <span className="rating-interval">{current.predicted_intervals?.[String(r)] || '?'}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
```

Write to `/Users/eric_zhou/Projects/vocabulary-notebook/frontend/src/components/SpacedReview.jsx`.

- [ ] **Step 2: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add frontend/src/components/SpacedReview.jsx
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): add SpacedReview component with 4 ratings + interval preview"
```

---

## Task 12: Add SpacedReview styles to App.css

**Files:**
- Modify: `frontend/src/App.css` (add styles)

- [ ] **Step 1: Add styles at end of file**

Append to `/Users/eric_zhou/Projects/vocabulary-notebook/frontend/src/App.css`:
```css
/* ─── Spaced Review ─────────────────────── */
.srs-container {
  max-width: 600px;
  margin: 0 auto;
}

.srs-progress {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.04em;
  margin-bottom: 16px;
  font-family: var(--font-display);
  font-style: italic;
}

.srs-rating-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 24px;
}

.srs-rating-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 14px 12px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  font-family: var(--font-body);
  transition:
    transform 0.15s var(--ease-out),
    background 0.15s var(--ease-out),
    border-color 0.15s var(--ease-out);
}

.srs-rating-btn:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
}

.srs-rating-btn .rating-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--heading);
  letter-spacing: 0.04em;
}

.srs-rating-btn .rating-interval {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  font-family: var(--font-display);
  font-style: italic;
}

.srs-rating-btn.rating-again  { border-left: 3px solid var(--error); }
.srs-rating-btn.rating-hard   { border-left: 3px solid var(--warn); }
.srs-rating-btn.rating-good   { border-left: 3px solid var(--success); }
.srs-rating-btn.rating-easy   { border-left: 3px solid var(--info); }

.srs-done {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-dim);
}

.srs-done h2 {
  font-family: var(--font-display);
  font-size: 28px;
  color: var(--heading);
  margin-bottom: 12px;
}

.srs-done p {
  font-size: 14px;
  color: var(--text-dim);
  margin-bottom: 8px;
}

.srs-done-hint {
  color: var(--accent) !important;
  font-style: italic;
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add frontend/src/App.css
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "style(srs): add SpacedReview grid + 4 rating button styles"
```

---

## Task 13: Update `Review.jsx` to use SpacedReview + add header

**Files:**
- Modify: `frontend/src/pages/Review.jsx` (full rewrite)

- [ ] **Step 1: Write the new Review.jsx**

```jsx
import { useState, useEffect, useCallback } from 'react'
import { fetchWords, fetchDates } from '../api'
import { useSSE } from '../useSSE'
import SpacedReview from '../components/SpacedReview'
import SpellingTest from '../components/SpellingTest'

const TABS = [
  { key: 'browse', label: '浏览' },
  { key: 'srs', label: '间隔复习' },
  { key: 'spelling', label: '拼写测试' },
]

export default function Review() {
  const [tab, setTab] = useState('browse')
  const [words, setWords] = useState([])
  const [dates, setDates] = useState([])
  const [date, setDate] = useState('')
  const [q, setQ] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  // SRS 状态
  const [srsCards, setSrsCards] = useState([])
  const [srsStats, setSrsStats] = useState(null)
  const [srsLoading, setSrsLoading] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => { fetchDates().then(d => setDates(d.dates)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    fetchWords({ q, date, size: 10000 })
      .then(data => setWords(data.words))
      .catch(() => setError('加载失败，请确认后端服务是否运行'))
      .finally(() => setLoading(false))
  }, [q, date])

  const handleEnriched = useCallback((wordId, data) => {
    setWords(prev => prev.map(w =>
      w.id === wordId ? { ...w, ...data } : w
    ))
  }, [])

  useSSE(handleEnriched)

  // SRS：拉取 due 队列
  const fetchSrsQueue = useCallback(async () => {
    setSrsLoading(true)
    try {
      const res = await fetch('/api/review/due?new_limit=20&limit=20')
      if (res.ok) {
        const data = await res.json()
        setSrsCards(data.cards)
        setSrsStats(data.stats)
      }
    } catch {
      setError('复习队列加载失败')
    } finally {
      setSrsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tab === 'srs') fetchSrsQueue()
  }, [tab, fetchSrsQueue])

  // 评分
  const handleRate = useCallback(async (wordId, rating) => {
    const res = await fetch(`/api/words/${wordId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || '评分失败')
    }
    return res.json()
  }, [])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const handleSessionEnd = useCallback(() => {
    fetchSrsQueue()
  }, [fetchSrsQueue])

  return (
    <div>
      {toast && <div className="toast toast-info">{toast}</div>}
      <div className="tabs">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'srs' && srsStats && (
        <div className="srs-header">
          {srsStats.due_today > 0
            ? <>今日待复习 <b>{srsStats.due_today}</b> · 全部 {srsStats.total}</>
            : <span className="srs-done-hint">今日已完成 ✓</span>}
        </div>
      )}

      {tab !== 'browse' && tab !== 'srs' && (
        <div className="toolbar">
          <input
            type="text" placeholder="筛选单词…" value={q}
            onChange={e => setQ(e.target.value)}
          />
          <select value={date} onChange={e => setDate(e.target.value)}>
            <option value="">全部日期</option>
            {dates.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      )}

      {error && <div className="empty-state"><p>{error}</p></div>}
      {!error && loading ? (
        <div className="loading">加载中…</div>
      ) : !error && words.length === 0 ? (
        <div className="empty-state"><p>没有单词可供复习</p></div>
      ) : tab === 'browse' ? (
        words.map(w => (
          <div key={w.id} className="word-card">
            <div className="head">
              <span className="word">{w.word}</span>
              {w.phonetic && <span className="phonetic">{w.phonetic}</span>}
            </div>
            <div className="definition">{w.definition}</div>
            {w.example && <div className="example-display">"{w.example}"</div>}
          </div>
        ))
      ) : tab === 'srs' ? (
        srsLoading ? (
          <div className="loading">加载复习队列…</div>
        ) : (
          <SpacedReview
            cards={srsCards}
            onRate={handleRate}
            onSessionEnd={handleSessionEnd}
          />
        )
      ) : (
        <SpellingTest words={words} />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Delete old Flashcard.jsx**

Run: `rm /Users/eric_zhou/Projects/vocabulary-notebook/frontend/src/components/Flashcard.jsx`

- [ ] **Step 3: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add frontend/src/pages/Review.jsx frontend/src/components/Flashcard.jsx
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): wire SpacedReview into Review page with stats header"
```

---

## Task 14: Add nav badge to App.jsx

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Add badge**

Find the nav block in `App.jsx` (around line 21-32). Replace the entire `app-nav` div with:
```jsx
        <nav className="app-nav">
          <Link to="/" className={location.pathname === '/' ? 'active' : ''}>
            单词列表
          </Link>
          <Link to="/review" className={location.pathname === '/review' ? 'active' : ''}>
            复习 {dueToday > 0 && <span className="nav-badge">{dueToday}</span>}
          </Link>
          <Link to="/word/new" className={location.pathname === '/word/new' ? 'active' : ''}>
            添加单词
          </Link>
          <ThemeToggle />
        </nav>
```

- [ ] **Step 2: Import and call useDueCount**

Replace the `export default function App() {` line and its body to add the hook. The full new file:
```jsx
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import WordList from './pages/WordList'
import WordNew from './pages/WordNew'
import WordDetail from './pages/WordDetail'
import Review from './pages/Review'
import ThemeToggle from './components/ThemeToggle'
import ModelStatus from './components/ModelStatus'
import { useDueCount } from './useDueCount'

export default function App() {
  const location = useLocation()
  const dueToday = useDueCount()

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1 className="app-title">
            <Link to="/">词汇笔记本</Link>
          </h1>
          <ModelStatus />
        </div>
        <nav className="app-nav">
          <Link to="/" className={location.pathname === '/' ? 'active' : ''}>
            单词列表
          </Link>
          <Link to="/review" className={location.pathname === '/review' ? 'active' : ''}>
            复习 {dueToday > 0 && <span className="nav-badge">{dueToday}</span>}
          </Link>
          <Link to="/word/new" className={location.pathname === '/word/new' ? 'active' : ''}>
            添加单词
          </Link>
          <ThemeToggle />
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<WordList />} />
          <Route path="/word/new" element={<WordNew />} />
          <Route path="/word/:id" element={<WordDetail />} />
          <Route path="/review" element={<Review />} />
        </Routes>
      </main>
    </div>
  )
}
```

- [ ] **Step 3: Add nav-badge CSS**

Append to `/Users/eric_zhou/Projects/vocabulary-notebook/frontend/src/App.css`:
```css
/* ─── Nav Badge ─────────────────────────── */
.nav-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 7px;
  background: var(--accent);
  color: var(--ink);
  border-radius: 9px;
  font-size: 10px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  vertical-align: 1px;
}
```

- [ ] **Step 4: Commit**

```bash
cd /Users/eric_zhou/Projects/vocabulary-notebook
git add frontend/src/App.jsx frontend/src/App.css
git -c user.name=Eric_Zhou -c user.email=eric_zhou@local commit -m "feat(srs): add due-today badge to nav with 60s polling"
```

---

## Task 15: Build frontend + end-to-end smoke test

**Files:** none (verification)

- [ ] **Step 1: Build frontend**

Run: `cd /Users/eric_zhou/Projects/vocabulary-notebook/frontend && npm run build 2>&1 | tail -8`
Expected: `built in ...ms` with no errors. Bundle should grow ~5-10 KB.

- [ ] **Step 2: Start backend**

Run: `cd /Users/eric_zhou/Projects/vocabulary-notebook && pkill -9 -f "Python app.py" 2>/dev/null; sleep 1; /Users/eric_zhou/Projects/vocabulary-notebook/.venv/bin/python app.py &`
Expected: backend running on port 1400 (wait 3s)

- [ ] **Step 3: Verify bundle has new code**

Run: `curl -s http://localhost:1400/ | grep -oE 'assets/index-[^"]+\.js' | head -1`
Expected: a `.js` path. Then verify the JS bundle contains `useDueCount` or `SpacedReview`:
Run: `curl -s http://localhost:1400/assets/$(curl -s http://localhost:1400/ | grep -oE 'index-[^"]+\.js' | head -1 | xargs basename) | grep -c -E "useDueCount|nav-badge|srs-rating"`
Expected: a count > 0

- [ ] **Step 4: Hit /api/review/due and inspect response shape**

Run: `curl -s "http://localhost:1400/api/review/due?new_limit=2&limit=3" | python3 -c "import json,sys; d=json.load(sys.stdin); c=d['cards'][0]; print('keys:', list(c.keys())); print('predicted:', c.get('predicted_intervals'))"`
Expected: keys include `id`, `word`, `definition`, `srs`, `predicted_intervals`. `predicted` has `{1, 2, 3, 4}`.

- [ ] **Step 5: Test full review cycle**

```bash
# Get a card
CARD=$(curl -s "http://localhost:1400/api/review/due?new_limit=1&limit=1" | python3 -c "import json,sys; print(json.load(sys.stdin)['cards'][0]['id'])")
echo "Card: $CARD"
# Rate it Good
curl -s -X POST "http://localhost:1400/api/words/$CARD/review" -H "Content-Type: application/json" -d '{"rating": 3}' | python3 -c "import json,sys; d=json.load(sys.stdin); s=d['word']['srs']; print('srs:', s); print('next_interval:', d['next_interval_seconds'])"
```
Expected: `srs` has `d`/`s`/`last_review_at`/`reps: 1`/`lapses: 0`. `next_interval_seconds > 0` (e.g., 432000 = 5d for Good on a new card).

- [ ] **Step 6: Kill backend**

Run: `pkill -9 -f "Python app.py"`

- [ ] **Step 7: Visual verification (user-driven)**

User should manually:
1. Open `http://localhost:1400/review` in browser
2. Click "间隔复习" tab
3. Verify header shows "今日待复习 X"
4. Click "空格" to flip a card
5. Verify 4 rating buttons appear with `(Xd)` previews
6. Press `3` to rate Good
7. Verify next card appears
8. Click "单词列表" — verify "复习 · N" badge in nav
9. (Optional) Complete a session to see the "本轮完成" screen

---

## Self-Review Notes

- Spec §1 data model: Task 4 (helpers) + Task 7 (POST review writes srs field) ✓
- Spec §2 endpoints: Tasks 5/6/7 (3 endpoints) ✓
- Spec §2 FSRS self-implement: Task 3 (fsrs.py with TDD) ✓
- Spec §2 _daily + new_limit: Task 4 (helpers) + Task 5 (stats) + Task 6 (due) + Task 7 (review increments) ✓
- Spec §3 SpacedReview replaces Flashcard: Task 11 (component) + Task 13 (page rewrite) + Task 13 step 2 (delete Flashcard.jsx) ✓
- Spec §3 4 buttons + interval preview: Task 11 component + Task 12 styles ✓
- Spec §3 keyboard 1-4: Task 11 handleKey ✓
- Spec §3 App nav badge: Task 14 ✓
- Spec §3 Review page header: Task 13 ✓
- Spec §4 lazy migration: no code needed — `word.get("srs")` returns None for words without srs field ✓
- Spec §4 new word order by created_at: Task 6 line `new_words.sort(key=lambda w: w["created_at"])` ✓
- Spec §4 review order by next_due_at: Task 6 line `review_words.sort(key=lambda w: w["_due_at"])` ✓
- Spec §4 Again re-queue same session: Task 11 `if (rating === 1 && isNew) { ... push(current) }` ✓
- Spec §4 exclude empty def: Task 5/6 filter `w.get("definition", "").strip()` ✓
- Spec §4 predicted_intervals: Task 6 (computed in `_predicted_intervals` helper) ✓

15 tasks. Estimated: ~3 hours of focused execution (each task 5-20 min).
