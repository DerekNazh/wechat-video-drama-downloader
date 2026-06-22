# 微信视频号后端服务 Client 设计

## 概述
实现一个 `WechatVideoAPIClient` 类，封装调用微信视频号后端服务（Go）的 HTTP 接口。

## 文件结构
```
core/service/
    __init__.py
    weixin_client.py    # 主实现
```

## 接口清单

| 方法 | 功能 | 返回 |
|------|------|------|
| `check_service()` | 检查 Go 后端服务是否在线 | `(bool, dict)` |
| `check_wechat()` | 检查微信是否已连接 | `(bool, dict)` |
| `create_task()` | 创建下载任务 | `task_id or None` |
| `get_task_status()` | 查询单个任务状态 | `status or None` |
| `cancel_task()` | 取消任务 | `bool` |

## 类设计

```python
class WechatVideoAPIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:2022", timeout: int = 30)
    
    def check_service(self) -> tuple[bool, dict]:
        """检查服务状态 /api/status"""
        
    def check_wechat(self) -> tuple[bool, dict]:
        """检查微信连接 /api/channels/contact/search"""
        
    def create_task(self, video_id: str, object_nonce_id: str, title: str, 
                  path: str, spec: str) -> str | None:
        """创建下载任务 /api/task/create"""
        
    def get_task_status(self, task_id: str) -> str | None:
        """查询任务状态 /api/task/profile"""
        
    def cancel_task(self, task_id: str) -> bool:
        """取消任务 /api/task/delete

        ⚠️ 注意事项：
        调用 cancel_task 后，如果本地视频文件已下载完成，**后端会删除本地视频文件**。
        测试时间：2026-04-23
        测试脚本：tests/集成测试/微信视频号后端服务和数据库服务/验证cancel_task是否删除本地文件.py
        测试结论：cancel_task 前文件存在（4.73 MB），cancel_task 后文件被删除。
        因此，如果需要保留已下载的视频文件，**不要调用 cancel_task**。""
    
    @staticmethod
    def check_process_exists() -> bool:
        """检查下载进程是否存在"""
```

## 错误处理
- 网络异常：返回 `(False, error_message)`，`None`
- HTTP 非 200：返回 `(False, None)` 并记录日志
- 超时：返回 `(False, None)`

## 配置
- 基础 URL：从 `settings.wx_api_base` 读取
- 超时：从 `settings.wx_api_timeout` 读取