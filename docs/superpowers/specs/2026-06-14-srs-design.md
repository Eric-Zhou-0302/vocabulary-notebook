# Spaced Repetition System (SRS) — 设计文档

**日期**: 2026-06-14
**状态**: 已批准，待实现

## 目标

把"词汇笔记本"从收藏夹变成学习工具。当前复习模式（闪卡 / 拼写）只是随机抽词，没有按遗忘曲线调度，效率低下。引入 **FSRS 算法** 做严肃的间隔复习（spaced repetition），让每次复习都踩在遗忘临界点上。

## 设计决策（已与用户确认）

| 维度 | 选择 | 理由 |
|---|---|---|
| 调度算法 | **FSRS**（社区默认权重，自实现 120 行） | 现代最优，相同记忆率下复习量比 SM-2 少 20-30% |
| 评分粒度 | **4 档**（重来 / 困难 / 良好 / 简单） | 与 FSRS 输入天然匹配；Anki 20+ 年验证有效 |
| UI 集成 | **替换闪卡 tab** 为"间隔复习" | 功能不冗余，一个 tab 一个职责 |
| 可见性 | **App nav 角标 + Review 顶部双显示** | 角标随时看见，详情进入即可看 |
| 新词入队 | **每日上限**（默认 20/天，可配置） | 避免一次性压 191 词造成启动负担 |

---

## §1 数据模型

每个 word 记录加一个 `srs` 子对象（用 `null` 表示"全新未学"）：

```json
{
  "id": "abc123",
  "word": "abandon",
  "definition": "vt. 放弃，抛弃",
  "phonetic": "/əˈbændən/",
  "example": "...",
  "created_at": "2026-06-14T10:00:00+08:00",
  "srs": {
    "d": 5.0,
    "s": 12.5,
    "last_review_at": "2026-06-14T10:30:00+08:00",
    "reps": 3,
    "lapses": 0
  }
}
```

字段说明：

| 字段 | 类型 | 含义 |
|---|---|---|
| `d` | float | FSRS Difficulty（1-10），初始默认 5.0 |
| `s` | float | FSRS Stability（天），新词为 0 |
| `last_review_at` | string \| null | ISO 8601 时间戳，最后复习时间 |
| `reps` | int | 累计复习次数 |
| `lapses` | int | 累计"重来"次数（识别"难词"的信号） |

**不存 review log**（FSRS 调参用的），v1 用社区训练好的默认权重。后续要重训再加。

**新词 vs 已学词**：
- `srs == null` → 全新，进新词队列（受每日上限约束）
- `srs != null` → 已学，进 review 队列（按 FSRS 排程）

**不存 `next_review_at`**，下次到期时间 = `last_review_at + interval(d, s, rating)`，需要时实时算。

---

## §2 后端 API

### 新增端点（3 个）

#### `GET /api/review/due?new_limit=20&limit=20`

返回下一批 due 卡片（混合新词 + 复习词）。

**Query 参数**：
- `new_limit`（可选，默认 20）— 新词每日上限
- `limit`（可选，默认 20）— 本次最多返回多少张卡

**响应**：
```json
{
  "cards": [
    {
      "id": "abc123",
      "word": "abandon",
      "definition": "vt. 放弃，抛弃",
      "phonetic": "/əˈbændən/",
      "example": "...",
      "srs": null,
      "predicted_intervals": {
        "1": "1m",
        "2": "1d",
        "3": "5d",
        "4": "10d"
      }
    }
  ],
  "stats": {
    "total": 191,
    "due_today": 12,
    "new_remaining": 175,
    "review_due": 4,
    "new_today": 5,
    "review_today": 3
  }
}
```

**排序**：
- 新词按 `created_at` 升序（最老的先复习）
- 复习词按 `last_review_at + computed_interval` 升序（最过期的先）
- 队列前 N 个是新词（受 `new_limit - new_today` 限制），后面是复习词

**排除**：定义非空的词才进入 due 列表（空定义还在 enrich 队列里的不算）。

#### `POST /api/words/{id}/review`

记录一次复习，更新 SRS 状态。

**Body**：
```json
{ "rating": 2 }   // 0=Again, 1=Hard, 2=Good, 3=Easy
```

**响应**：
```json
{
  "word": { "id": "abc123", "word": "abandon", ..., "srs": {...} },
  "next_interval_seconds": 432000   // 5d；前端用此展示"下次 Xd"，不存盘
}
```

**副作用**：
- 写回 `words.json`（更新 `srs` 字段）
- 累计 `_daily` 计数器（跨日自动重置）

#### `GET /api/review/stats`

轻量端点，App nav 角标专用（每 60s 轮询）。

**响应**：
```json
{
  "total": 191,
  "due_today": 12,
  "new_remaining": 175,
  "review_due": 4,
  "new_today": 5,
  "review_today": 3
}
```

### FSRS 算法实现

新增 `app.py` 同级模块（或者直接在 `app.py` 里写一段）：

```python
# fsrs.py — 简化版 FSRS（用社区默认权重）
W = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]
DECAY = -0.5
FACTOR = 19/81

def retrievability(d, s, elapsed_days):
    return (1 + FACTOR * elapsed_days / s) ** DECAY

def next_interval(d, s, r, rating):
    """返回新 interval（秒）"""
    ...

def update(d, s, r, rating, elapsed_days):
    """返回 (new_d, new_s)"""
    ...
```

完整实现参考 [open-spaced-repetition/fsrs4anki](https://github.com/open-spaced-repetition/fsrs4anki) 论文与公式表。

### 全局状态

新增一个 `_daily` 字典（与现有 `_enrich_*` globals 同位置）：

```python
_daily: dict = {
    "date": "",      # YYYY-MM-DD (Beijing)
    "new_today": 0,
    "review_today": 0,
}
```

- 每次 `POST /review` 时：跨日则重置；`srs was null` → `new_today++`，否则 `review_today++`
- `new_due_today = max(0, new_limit - new_today)`

### 路由顺序

`/api/words/{word_id}/review` 这条路径如果放在 `/api/words/{word_id}` 之后，会被吞成 word_id 匹配。**新端点必须放在 `get_word` 路由之前**。沿用现有 `enrich-missing` 的注释约定。

---

## §3 前端

### 替换闪卡 tab

`Review.jsx` 里的 TABS 把 `'flashcard'` 改名为 `'srs'`，label 改为"间隔复习"。`Flashcard.jsx` 删除，替换为 `SpacedReview.jsx`。

### SpacedReview.jsx 核心交互

```
┌─────────────────────────────────────┐
│   间隔复习  ·  今日待复习 12 / 全部 191 │
├─────────────────────────────────────┤
│                                     │
│           abandon                   │
│           /əˈbændən/                │
│                                     │
│      [按空格键显示释义]              │
│                                     │
├─────────────────────────────────────┤
│  释义显示后露出：                     │
│  [ 重来 (1m) ][ 困难 (2d) ]         │  ← 4 档按钮
│  [ 良好 (5d) ][ 简单 (10d) ]         │  ← 带下次间隔预览
└─────────────────────────────────────┘
```

**键盘**：
- `Space` 翻面（显示释义 + 例句）
- `1` / `2` / `3` / `4` 评分（翻面后才生效）

**按钮设计**：
| Key | 标签 | 颜色 token | 行为 |
|---|---|---|---|
| 1 | 重来 | `--error` (红 `#c45a4a`) | 立即重进当前 session 队列末尾，`lapses++` |
| 2 | 困难 | `--warn` (橙 `#d68a3a`，**新加** 进 `[data-theme="dark"]` 和 `[data-theme="light"]`) | 短间隔，D 微调 |
| 3 | 良好 | `--success` (绿 `#7aa365`) | 标准间隔 |
| 4 | 简单 | `--info` (蓝 `#5a85b8`，**新加**) | 长间隔 |

按钮上的 `(Xd)` 是 **FSRS 在 `/api/review/due` 响应时计算好的预览**（存在 `predicted_intervals` 字段），卡片出队到队列时已算好，渲染时直接展示。让用户明白每个选择的后果。

### 一轮结束

- 显示 "本轮复习 X 个（新词 Y / 复习 Z）"
- "再复习 X 个" 按钮（再次调 `/api/review/due`，继续消费 due 队列）
- "回到列表" 链接 → 切到 `browse` tab

### App nav 角标

`App.jsx` 顶 nav 的"复习"链接旁加 `· 12` 角标（金色，不抢戏）。

**实现**：新增 `useDueCount` hook，每 60s 轮询一次 `/api/review/stats`，取 `due_today` 显示。

### Review 页面头部

`Review.jsx` tabs 下方加一行：

```
今日待复习 12 / 全部 191
```

归零时显示 `今日已完成 ✓`（用 `--success` 绿色调）。

### CSS 复用

- 闪卡翻面动画（`.flashcard` / `.flashcard-inner` / `.flipped`）直接复用
- 4 档按钮加新样式 `.srs-rating-grid` + `.srs-rating-btn`（用现有 `.btn` 变体）
- 颜色变量用 `--error` / `--success` / `--accent` 等现有 token

---

## §4 迁移 + 边界

### 迁移策略（lazy）

- **不动 words.json**。读单词时如果没 `srs` 字段 → 当作 `null`（新词）处理
- **写回时**（review 后）才显式写入 `srs: {...}` 字段
- 现有 191 词一夜成为"新词池"，进入复习队列

### 新词顺序

按 `created_at` 升序（最老的先复习），保证"新词慢慢进"而不是"刚加的立刻顶替旧的"。

### 复习词顺序

按 `last_review_at + computed_interval` 升序（最过期的先复习）。

### Again 行为

在当前 session 队列末尾再插入一次（同 session 内重学），同时 `lapses++`。前端维护一个本地队列副本，Again 时 push 一次。

### 边界情况

| 场景 | 行为 |
|---|---|
| 空定义词 | 排除在 review 之外（还在 enrich 队列里的不算） |
| 单词删除 | SRS 状态一起消失（可接受） |
| 单词释义被编辑 | SRS 状态保留（用户已经"知道"这个词） |
| 单词新建 | `srs: null` + 加入新词队列（按 `created_at` 顺序） |
| API 调用失败 | 弹 toast 提示，卡片不前进，用户重试 |
| 多 tab 同时打开 | v1 不处理（个人使用罕见） |
| 时区 | 沿用现有 `CHINA_TZ`，每日边界按北京时间 |
| 导出（JSON/CSV/PDF） | 不过滤 SRS 字段（备份/迁移用得到） |
| 导入（如果有） | 无 srs 字段 → 视为新词 |

### "下次间隔"预览计算

服务端在 `/api/review/due` 返回每张卡的 `predicted_intervals: {1, 2, 3, 4}`，key 是 rating 0-3，value 是格式化字符串（`"1m"` / `"5d"` / `"2mo"`）。

对 `srs == null` 的新词：直接用 FSRS 的"学习阶段"默认值（Again=1m, Hard=1d, Good=5d, Easy=10d 是经验值，会随权重微调）。

---

## §5 实施切片（建议执行顺序）

1. **后端** `fsrs.py` — 算法模块（自实现，独立可测）
2. **后端** `_daily` 全局状态 + 跨日重置逻辑
3. **后端** `GET /api/review/due` + `GET /api/review/stats`
4. **后端** `POST /api/words/{id}/review`
5. **后端** 端到端测试（curl 模拟完整流程：拿卡 → 评分 → 看新状态 → 再次拿卡）
6. **前端** `SpacedReview.jsx`（替换 Flashcard）+ 4 档按钮 + 键盘
7. **前端** `useDueCount` hook + App nav 角标
8. **前端** Review 页面头部计数
9. **端到端验证**：浏览器点开 Review → 走完一轮 → 看 nav 角标变化

## 不做（v1 scope 外）

- 难词本 / Lapse 自适应
- 复习统计图表
- 复习日历热力图
- 自定义每日上限 UI（先用 `config.json` 常量）
- 移动端专属布局（沿用现有响应式）
- 离线模式
- 复习历史 / 调参
