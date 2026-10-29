"""宽容解析五件套 + 重名配对 + total=0 三态（YZPQ-322）。

全部纯函数，对畸形/缺字段响应不崩，给出降级与告警。
"""
from __future__ import annotations

REQUIRED_FIELDS = ["items", "total"]


def safe_get(d: dict, *keys, default=None):
    """.get() 链，任一节点非 dict/缺失 -> default。"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def missing_required(payload: dict) -> list[str]:
    """关键字段缺失清单（告警用）。"""
    return [f for f in REQUIRED_FIELDS if f not in payload]


def classify_total_zero(items, empty_reason: str | None) -> str:
    """total=0 三态：normal_items / bad_input / truly_empty。"""
    if items:
        return "normal_items"
    if empty_reason == "bad_input":
        return "bad_input"  # 无效作者/链接
    return "truly_empty"     # 真空账号


def pair_by_unique_id(nickname: str, candidates: list[dict],
                      pairing_cache: dict) -> dict | None:
    """重名配对：唯一 ID 锚定；缓存命中直接返回，否则返回候选首项并写缓存。"""
    if nickname in pairing_cache:
        return pairing_cache[nickname]
    if not candidates:
        return None
    chosen = candidates[0]
    pairing_cache[nickname] = chosen
    return chosen


CONFIRM_TTL_SEC = 7 * 24 * 3600  # 7 天空确认免补
