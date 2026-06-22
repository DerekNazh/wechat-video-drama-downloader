"""全局事件总线

解耦事件产生者和消费者，所有模块都能往里塞事件。
SSE 端点从这里消费，推送给前端。
"""

import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger("event_bus")

# === 事件常量 ===
GO_CONNECTED = "go_connected"
GO_DISCONNECTED = "go_disconnected"
TASKS_RESUMED = "tasks_resumed"


class EventBus:
    """事件总线类，支持事件订阅和 Go 后端连接状态管理"""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._go_online: bool = False

    @property
    def go_online(self) -> bool:
        """获取当前 Go 后端连接状态"""
        return self._go_online

    def subscribe(self, event: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """订阅特定事件

        Args:
            event: 事件类型
            callback: 回调函数，接收事件数据 dict
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        logger.info(f"[EventBus] 订阅事件 '{event}': {getattr(callback, '__name__', repr(callback))}, 当前共 {len(self._listeners[event])} 个监听器")

    def unsubscribe(self, event: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """取消订阅特定事件

        Args:
            event: 事件类型
            callback: 要移除的回调函数
        """
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)
            logger.info(f"[EventBus] 取消订阅事件 '{event}', 剩余 {len(self._listeners[event])} 个监听器")

    def emit(self, event: str, data: Dict[str, Any]) -> None:
        """发布事件

        Args:
            event: 事件类型
            data: 事件数据 dict
        """
        payload = {"event_type": event, **data}
        listeners = self._listeners.get(event, [])
        logger.debug(f"[EventBus] 发布事件: type={event}, 监听器={len(listeners)}")
        for cb in listeners:
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"[EventBus] 监听器异常: {e}")

    def set_go_online(self, online: bool) -> None:
        """设置 Go 后端连接状态，状态变化时自动发布事件

        Args:
            online: True 表示已连接，False 表示已断开
        """
        if self._go_online == online:
            logger.debug(f"[EventBus] Go 连接状态未变化: {online}")
            return

        self._go_online = online
        event = GO_CONNECTED if online else GO_DISCONNECTED
        logger.info(f"[EventBus] Go 连接状态变化: {online}, 发布事件 {event}")
        self.emit(event, {"online": online})


# === 全局单例 ===
_event_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局 EventBus 单例"""
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance


# === 向后兼容：旧的全局函数式 API ===

_legacy_listeners: List[Callable] = []


def subscribe(callback):
    """注册事件回调（SSE 端点启动时调用）- 向后兼容"""
    _legacy_listeners.append(callback)
    logger.info(f"[event_bus] 注册监听器: {getattr(callback, '__name__', repr(callback))}, 当前共 {len(_legacy_listeners)} 个")


def unsubscribe(callback):
    """移除事件回调（SSE 端点断开时调用）- 向后兼容"""
    if callback in _legacy_listeners:
        _legacy_listeners.remove(callback)
        logger.info(f"[event_bus] 移除监听器, 剩余 {len(_legacy_listeners)} 个")


def emit(event_type: str, data: dict):
    """发射事件，通知所有监听器 - 向后兼容

    Args:
        event_type: 事件类型，如 "task_completed", "monitor_status", "video_synced"
        data: 事件数据 dict
    """
    payload = {"event_type": event_type, **data}
    for cb in _legacy_listeners:
        try:
            cb(payload)
        except Exception as e:
            logger.error(f"[event_bus] 监听器异常: {e}")


# === 向后兼容：旧代码仍在用的函数 ===

def emit_task_completed(data: dict):
    """兼容旧调用：emit("task_completed", data)"""
    emit("task_completed", data)


def emit_task_failed(data: dict):
    """任务失败时通知前端"""
    emit("task_failed", data)


def on_task_completed(callback):
    """兼容旧调用：subscribe(callback)"""
    subscribe(callback)


def _clear_listeners():
    """清空所有监听器（仅供测试使用）"""
    _legacy_listeners.clear()


def _get_listeners():
    """获取监听器列表引用"""
    return _legacy_listeners
