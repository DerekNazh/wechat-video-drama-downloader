"""熔断器 + usage 记账（YZPQ-321）。

熔断器：同供应商连续失败>=3 -> OPEN 60s -> HALF_OPEN 放行1探测请求 -> 成功CLOSED/失败再OPEN。
开关 fallback_enabled=False 时熔断恒 CLOSED（不熔断）。
"""
from __future__ import annotations

from collections import defaultdict

THRESHOLD = 3
OPEN_SEC = 60.0


class CircuitBreaker:
    def __init__(self, now=__import__("time").monotonic, enabled: bool = True):
        self.now = now
        self.enabled = enabled
        self.fail: dict[str, int] = defaultdict(int)
        self.state: dict[str, str] = defaultdict(lambda: "CLOSED")
        self.opened_at: dict[str, float] = {}

    def allow(self, supplier: str) -> bool:
        if not self.enabled:
            return True
        st = self.state[supplier]
        if st == "CLOSED":
            return True
        if st == "OPEN":
            if self.now() - self.opened_at[supplier] >= OPEN_SEC:
                self.state[supplier] = "HALF_OPEN"
                return True  # 半开放行1探测
            return False
        if st == "HALF_OPEN":
            return False  # 半开只允许1个，其余拒绝
        return True

    def record_success(self, supplier: str):
        self.fail[supplier] = 0
        self.state[supplier] = "CLOSED"

    def record_failure(self, supplier: str):
        if not self.enabled:
            return
        self.fail[supplier] += 1
        if self.state[supplier] == "HALF_OPEN":
            self.state[supplier] = "OPEN"
            self.opened_at[supplier] = self.now()
        elif self.fail[supplier] >= THRESHOLD:
            self.state[supplier] = "OPEN"
            self.opened_at[supplier] = self.now()


def record_usage(log: list, supplier: str, endpoint: str,
                 duration_ms: float, status: int | None,
                 cache_layer: str = "api", key_invalid: bool = False):
    """每次调用落 api_usage（这里 append 到传入 list，持久化由 DAO 接）。"""
    log.append({
        "supplier": supplier, "endpoint": endpoint,
        "duration_ms": round(duration_ms, 2), "status": status,
        "cache_layer": cache_layer, "key_invalid": key_invalid,
    })
