// ==================== 前端状态数据库 - 统一入口 ====================

// 表操作
import { find, where, all, on, off, emit } from './db.js';

// 作者表
import {
  get as getAuthor,
  all as getAuthors,
  update as updateAuthor,
  setAll as setAuthors
} from './tables/authors.js';

// 视频表
import {
  get as getVideo,
  getAuthorVideos,
  all as getVideos,
  update as updateVideo,
  setAuthorVideos,
  removeAuthorVideos
} from './tables/videos.js';

// 任务表
import {
  get as getTask,
  all as getTasks,
  find as findTasks,
  getByVideoId,
  getRunning,
  update as updateTask,
  setAll as setTasks,
  cancel as cancelTask
} from './tables/tasks.js';

// ==================== 统计（实时计算） ====================

// 实时计算作者统计
export function getAuthorCatalog(username) {
  const videos = getAuthorVideos(username);
  const total = videos.length;
  const downloaded = videos.filter(v => v.is_downloaded === 1).length;
  const pending = total - downloaded;
  const progress = total > 0 ? Math.round((downloaded / total) * 100) : 0;

  return { total, downloaded, pending, progress };
}

// ==================== 初始化数据 ====================

import { getAllAuthorsWithVideos } from '../video.js';
import { getTaskList } from '../task.js';

// 从 API 加载所有数据
export async function initFromAPI() {
  // 加载作者和视频
  const videoRes = await getAllAuthorsWithVideos();
  if (videoRes.code === 0 && videoRes.data) {
    videoRes.data.forEach(item => {
      const author = item.author;
      const authorVideos = item.videos;

      setAuthors([author]);
      setAuthorVideos(author.id, authorVideos);
    });
  }

  // 加载任务
  const taskRes = await getTaskList();
  if (taskRes.code === 0 && taskRes.data) {
    setTasks(taskRes.data.list || []);
  }
}

// ==================== 导出 ====================

// 查询
export { find, where, all };

// 作者
export { getAuthor, getAuthors, updateAuthor, setAuthors };

// 视频
export { getVideo, getAuthorVideos, getVideos, updateVideo, setAuthorVideos, removeAuthorVideos };

// 任务
export { getTask, getTasks, findTasks, getByVideoId, getRunning, updateTask, setTasks, cancelTask };

// 统计（实时计算）
export { getAuthorCatalog };

// 事件
export { on, off, emit };

// 批量操作
export { initFromAPI };

// 便捷函数
export function getCurrentAuthorVideos(username) {
  return getAuthorVideos(username);
}

export function getCurrentAuthorCatalog(username) {
  return getAuthorCatalog(username);
}