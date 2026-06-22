"""数据模型定义"""

from dataclasses import dataclass, fields
from typing import Optional, TypeVar

T = TypeVar('T')


def copy_instance(self: T) -> T:
    """复制实例"""
    return self.__class__(*[getattr(self, f.name) for f in fields(self)])


@dataclass
class Author:
    """作者"""
    id: str                          # 随机唯一字符串
    source_author_id: Optional[str]   # 来源作者ID（视频号原始ID / username）
    name: str                        # 作者名称 / nickname
    tag: Optional[str]               # 标签
    bio: Optional[str]               # 简介 / signature
    avatar_url: Optional[str]        # 头像URL / headUrl
    cover_img_url: Optional[str]     # 封面图URL / coverImgUrl
    created_at: str                  # 创建时间
    updated_at: str                  # 更新时间
    latest_publish_date: Optional[str] = None  # 最新视频发布时间（监控基准）
    copy = copy_instance


@dataclass
class AuthorVideo:
    """作者视频"""
    video_id: str                    # 视频ID / id
    author_id: str                    # 作者ID
    title: str                       # 标题 / objectDesc.description
    object_nonce_id: str             # 视频 Nonce ID / objectNonceId
    url: str                         # 视频直链 / media[].url + urlToken
    spec: str                        # 视频规格 / media[].spec
    file_size: int                   # 文件大小 / media[].fileSize
    cover_url: str                   # 封面图URL / media[].coverUrl
    decode_key: int                  # 解密密钥 / media[].decodeKey
    author_avatar: str               # 作者头像 / contact.headUrl
    duration: int                    # 时长（秒） / media[].videoPlayLen (毫秒转秒)
    create_time: str                 # 发布时间 / createtime (时间戳转字符串)
    is_downloaded: int               # 是否已下载 (0/1)
    download_path: str               # 下载路径
    downloaded_at: Optional[str] = None  # 下载完成时间（ALTER TABLE迁移）
    video_type: str = "short_video"      # "short_video" 或 "live_replay"（ALTER TABLE迁移）
    copy = copy_instance


@dataclass
class DownloadTask:
    """下载任务"""
    task_id: str                     # 任务ID（对应Go后端的id）
    video_id: str                    # 视频ID
    url: str                         # 视频URL
    title: str                       # 标题
    filename: str                    # 文件名（不含后缀）
    spec: str                        # 视频规格
    suffix: str                       # 文件后缀
    key: int                         # 解密密钥
    status: str                      # 状态: pending/running/completed/failed
    progress: int                    # 进度百分比
    downloaded: int                  # 已下载字节
    total_size: int                  # 总大小
    speed: int                       # 下载速度
    error_msg: str                   # 错误信息
    created_at: str                  # 创建时间
    updated_at: str                  # 更新时间
    completed_at: Optional[str] = None    # 完成时间（ALTER TABLE迁移）
    video_type: str = "short_video"       # 从关联的 author_video 继承（ALTER TABLE迁移）
    create_time: str = ""                 # 视频发布时间（ALTER TABLE迁移）
    copy = copy_instance
