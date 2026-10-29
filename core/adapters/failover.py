"""失败分类 + 转备决策（YZPQ-320）：纯查表，无 if 判断分支外逻辑。

分类动作三态：
- failover: 转备供应商（主备映射表切换）
- backoff: 指数退避不转备（429）
- none: 不重试不转备（读超时，防双计费）
"""
from __future__ import annotations

# 主备能力映射（能力 -> [主, 备]）
PRIMARY_BACKUP = {
    "search": ["tikhub", "honghu"],
    "detail": ["tikhub", "honghu"],
    "download": ["tikhub", "honghu"],
}

# 400 端点查表：平台侧故障 -> 红狐替代
BAD_REQUEST_ENDPOINTS_TO_BACKUP = {"fetch_search_videos", "get_user_works"}


def classify(status: int | None, kind: str) -> str:
    """kind: conn / http / read_timeout。返回 failover|backoff|none。"""
    if kind == "read_timeout":
        return "none"  # 读超时不重试不转备，防双计费
    if kind == "conn":
        return "failover"
    # http
    if status is None:
        return "failover"
    if 500 <= status < 600:
        return "failover"
    if status == 429:
        return "backoff"
    if status in (401, 402):
        return "failover"
    if status == 400:
        return "failover"  # 400 由调用方按端点表决定是否红狐替代，这里默认转备
    return "none"


def backoff_delay(attempt: int) -> float:
    """429 指数退避 2/4/8s。"""
    return float(2 ** (min(attempt, 2) + 1))


def pick_backup(capability: str, current: str) -> str | None:
    """主备映射表切换；无备用返回 None。"""
    chain = PRIMARY_BACKUP.get(capability, [])
    if len(chain) < 2:
        return None
    return chain[1] if current == chain[0] else chain[0]
