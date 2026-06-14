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


def next_interval(s: float, request_retention: float = REQUEST_RETENTION) -> float:
    """根据稳定性和目标回忆率，计算下次复习间隔（天）。

    测试接口名: next_interval（输入稳定性 S，输出天数）。
    """
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
