"""落盘后文件层 L5 校验（YZPQ-309）。

权威=文件系统：stat 存在 + 大小>0 + 与下载记录字节一致。
与 308（网络层 Content-Length 对齐）各管一层，不互相替代。
"""
from __future__ import annotations

import os
from typing import Optional


def l5_verify(path: str, expected_bytes: Optional[int] = None) -> bool:
    """文件存在 + 大小>0 + (若给 expected_bytes) 字节一致。"""
    if not path or not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    if size <= 0:
        return False
    if expected_bytes is not None and size != expected_bytes:
        return False
    return True
