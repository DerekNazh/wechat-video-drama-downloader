"""视频处理工具函数"""

import random
import string
import logging

logger = logging.getLogger("video_utils")


def generate_random_suffix(length: int = 4) -> str:
    """生成随机字符串后缀

    Args:
        length: 随机字符长度，默认4位

    Returns:
        格式如 '_a1b2'
    """
    chars = string.ascii_lowercase + string.digits
    suffix = ''.join(random.choice(chars) for _ in range(length))
    return f"_{suffix}"


def deduplicate_by_title(items: list[dict], title_key: str = "title") -> list[dict]:
    """第一轮去重：去除列表内部标题重复的项

    保留第一个遇到的，丢弃后续重复的，保持原有顺序。

    Args:
        items: 待去重的字典列表
        title_key: 标题字段的 key，默认 "title"

    Returns:
        去重后的列表
    """
    if not items:
        return []

    seen_titles = set()
    result = []
    duplicate_count = 0

    for item in items:
        title = item.get(title_key, "")
        if title not in seen_titles:
            seen_titles.add(title)
            result.append(item)
        else:
            duplicate_count += 1

    if duplicate_count > 0:
        logger.info(f"[deduplicate_by_title] 去除列表内部重复标题: {duplicate_count} 个")

    return result


def resolve_duplicate_title(
    item: dict,
    existing_titles: set[str],
    title_key: str = "title"
) -> tuple[dict, bool]:
    """第二轮去重：检查标题是否与已有集合重复

    如果重复，追加随机后缀。

    Args:
        item: 待处理的字典
        existing_titles: 已存在的标题集合
        title_key: 标题字段的 key

    Returns:
        (处理后的字典, 是否追加了后缀)
    """
    title = item.get(title_key, "")

    if not title:
        return item, False

    if title not in existing_titles:
        return item, False

    # 标题重复，追加随机后缀
    suffix = generate_random_suffix(4)
    new_title = f"{title}{suffix}"

    # 确保新标题不重复（罕见情况：随机后缀也冲突）
    max_attempts = 10
    attempts = 0
    while new_title in existing_titles and attempts < max_attempts:
        suffix = generate_random_suffix(4)
        new_title = f"{title}{suffix}"
        attempts += 1

    if attempts >= max_attempts:
        logger.warning(f"[resolve_duplicate_title] 随机后缀冲突多次: {title}")

    # 复制字典并替换标题
    result = item.copy()
    result[title_key] = new_title
    existing_titles.add(new_title)  # 加入集合，避免连续重复

    logger.debug(f"[resolve_duplicate_title] 标题去重: '{title}' -> '{new_title}'")

    return result, True


def resolve_all_duplicate_titles(
    items: list[dict],
    existing_titles: set[str],
    title_key: str = "title"
) -> list[dict]:
    """批量处理标题去重

    Args:
        items: 待处理的字典列表
        existing_titles: 已存在的标题集合
        title_key: 标题字段的 key

    Returns:
        处理后的列表
    """
    if not items:
        return []

    result = []
    resolved_count = 0

    # 复制集合，避免修改原集合
    titles_set = existing_titles.copy()

    for item in items:
        resolved_item, was_resolved = resolve_duplicate_title(item, titles_set, title_key)
        result.append(resolved_item)
        if was_resolved:
            resolved_count += 1

    if resolved_count > 0:
        logger.info(f"[resolve_all_duplicate_titles] 处理与数据库重复标题: {resolved_count} 个")

    return result
