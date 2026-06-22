// ==================== 响应式数据状态管理器 ====================
// 数据变化时自动调用订阅的回调

// 存储所有数据
const _state = {
  authors: [],        // Author[] - 所有作者
  catalog: {},        // { username: { total, downloaded, pending, progress } }
  videos: {},        // { username: { videos: { video_id: Video } } }
  tasks: []          // Task[] - 活跃任务
};

// 存储任务的回调函数
const _subscribers = {
  authors: [],
  catalog: [],
  videos: [],
  tasks: []
};

// 订阅数据变化
export function subscribe(key, callback) {
  if (_subscribers[key]) {
    _subscribers[key].push(callback);
  }
}

// 取消订阅
export function unsubscribe(key, callback) {
  if (_subscribers[key]) {
    _subscribers[key] = _subscribers[key].filter(cb => cb !== callback);
  }
}

// 通知所有订阅者
function notify(key, data) {
  if (_subscribers[key]) {
    _subscribers[key].forEach(cb => cb(data));
  }
}

// ============ Authors ============

// 设置作者列表
export function setAuthors(authors) {
  _state.authors = authors;
  notify('authors', authors);
}

// 获取作者列表
export function getAuthors() {
  return _state.authors;
}

// 获取单个作者
export function getAuthor(username) {
  return _state.authors.find(a => a.id === username);
}

// ============ Catalog ============

// 设置目录
export function setCatalog(catalog) {
  _state.catalog = catalog;
  notify('catalog', catalog);
}

// 获取目录
export function getCatalog() {
  return _state.catalog;
}

// 获取作者统计
export function getAuthorCatalog(username) {
  return _state.catalog[username];
}

// ============ Videos ============

// 设置视频
export function setVideos(username, videos) {
  _state.videos[username] = videos;
  notify('videos', _state.videos);
}

// 获取视频
export function getVideos(username) {
  return _state.videos[username]?.videos || {};
}

// 获取单个视频
export function getVideo(username, videoId) {
  return _state.videos[username]?.videos?.[videoId];
}

// ============ Tasks ============

// 设置任务
export function setTasks(tasks) {
  _state.tasks = tasks;
  notify('tasks', tasks);
}

// 获取任务
export function getTasks() {
  return _state.tasks;
}

// 获取单个任务的进度
export function getTaskProgress(videoId) {
  return _state.tasks.find(t => t.video_id === videoId);
}

// ============ 初始化数据（从 API 获取）============

import { getAllAuthorsWithVideos } from '../video.js';

// 初始化所有数据
export async function initData() {
  const res = await getAllAuthorsWithVideos();
  if (res.code === 0 && res.data) {
    const authors = [];
    const catalog = {};
    const videos = {};

    res.data.forEach(item => {
      const author = item.author;
      const authorVideos = item.videos;

      authors.push(author);

      // 统计
      const total = authorVideos.length;
      const downloaded = authorVideos.filter(v => v.is_downloaded === 1).length;
      const pending = total - downloaded;
      const progress = total > 0 ? Math.round((downloaded / total) * 100) : 0;
      catalog[author.id] = { total, downloaded, pending, progress };

      // 视频
      const videoMap = {};
      authorVideos.forEach(v => {
        videoMap[v.video_id] = v;
      });
      videos[author.id] = { videos: videoMap };
    });

    setAuthors(authors);
    setCatalog(catalog);
    setVideosData(videos);
  }
}

// 辅助函数：设置所有视频
function setVideosData(videosData) {
  _state.videos = videosData;
  notify('videos', videosData);
}

// 获取所有视频
export function getVideosData() {
  return _state.videos;
}