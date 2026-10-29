"""断点续传 · Range 逻辑（YZPQ-308，网络层字节对齐）。

纯逻辑层：不真发 HTTP，只算 Range 头、判 416、做 Content-Length/Content-Range
字节对齐。真正的请求由下载引擎在调用时接入。
"""
from __future__ import annotations

from typing import Optional


def supports_range(accept_ranges: Optional[str]) -> bool:
    return bool(accept_ranges and "bytes" in accept_ranges.lower())


def plan_resume(part_bytes: int, accept_ranges: Optional[str]) -> dict:
    """给定 .part 已落盘字节数，决定怎么下。

    返回 {"mode": "range"|"restart", "headers": {...}}
    """
    if part_bytes > 0 and supports_range(accept_ranges):
        return {"mode": "range",
                "headers": {"Range": f"bytes={part_bytes}-"}}
    return {"mode": "restart", "headers": {}}


def is_416(status: int) -> bool:
    return status == 416


def align_total(content_length: Optional[str],
                content_range: Optional[str],
                resume_from: int = 0) -> Optional[int]:
    """从响应头解析总字节数（Content-Range 优先，形如 bytes 0-99/200）。"""
    if content_range and "/" in content_range:
        try:
            total = content_range.split("/")[-1].strip()
            if total != "*":
                return int(total)
        except ValueError:
            pass
    if content_length and content_length.isdigit():
        # range 响应只给剩余字节数，总=已下载+本段
        return resume_from + int(content_length)
    return None


def byte_aligned(expected_total: Optional[int], final_bytes_on_disk: int) -> bool:
    """下载完成做字节对齐校验（权威）。expected_total 未知则放宽为 >0。"""
    if final_bytes_on_disk <= 0:
        return False
    if expected_total is None:
        return True
    return final_bytes_on_disk == expected_total
