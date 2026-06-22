// ==================== 全局状态 ====================
let uptimeTimer = null;

let syncInterval = 1800000; // 新视频同步轮询间隔（30分钟）
let syncTimer = null;
let _lastVideoFilter = '';

// ==================== 全局状态变量（供 migrated 文件使用） ====================
let _adsEnabled = true;  // 广告开关，由 initConfig 设置
let _allAuthors = [];
let _catalogData = [];
let _authorVideosData = {};
let _activeTasks = [];
let _currentAuthor = null;
let _currentPage = 'home';
let _selectedVideos = new Set();
let _goOnline = false;
let _serviceState = 'stopped';
let _monitorRunning = false;
let _sseConnected = false;
let _fallbackPollInterval = null;
let _taskResumeRetryTimer = null;
let _taskResumeRetryCount = 0;
const MAX_TASK_RESUME_RETRIES = 6;

// ==================== rAF 批量更新 ====================
let _rafQueued = false;
let _rafCallbacks = [];

function scheduleUIUpdate(fn) {
  _rafCallbacks.push(fn);
  if (!_rafQueued) {
    _rafQueued = true;
    requestAnimationFrame(flushUIUpdates);
  }
}

function flushUIUpdates() {
  _rafQueued = false;
  const callbacks = _rafCallbacks;
  _rafCallbacks = [];
  callbacks.forEach(fn => {
    try { fn(); } catch (e) { console.error('flushUIUpdates:', e); }
  });
}

// ==================== 字段映射：后端数据 → 前端格式 ====================

function mapAuthor(raw) {
  var username = raw.source_author_id;
  return {
    username: username,
    nickname: raw.name,
    head_url: username ? '/api/video/avatar/' + encodeURIComponent(username) : '',
    profession: raw.tag,
    signature: raw.bio,
    id: raw.id,
  };
}

function mapVideo(raw) {
  return {
    id: raw.video_id,
    video_id: raw.video_id,
    video_type: raw.video_type || 'short_video',
    title: raw.title,
    duration: raw.duration,
    cover_url: raw.cover_url,
    size: raw.file_size,
    actual_size: raw.file_size,
    downloaded: raw.is_downloaded === 1,
    download_path: raw.download_path,
    create_time: raw.create_time,
    author_avatar: raw.author_avatar,
    author_id: raw.author_id,
    spec: raw.spec,
  };
}

// ==================== 初始化：加载配置并启动应用 ====================

async function initConfig() {
  try {
    const resp = await fetch("/api/service/config");
    if (resp.ok) {
      const config = await resp.json();
      // 设置配置值到对应的输入框
      if (config.doc_sync_interval !== undefined) {
        const el = document.getElementById('settingDocSyncInterval');
        if (el) el.value = config.doc_sync_interval;
      }
      if (config.wx_status_interval !== undefined) {
        const el = document.getElementById('settingStatusInterval');
        if (el) el.value = config.wx_status_interval;
      }
      if (config.max_concurrent !== undefined) {
        const el = document.getElementById('settingMaxConcurrent');
        if (el) el.value = config.max_concurrent;
      }
      if (config.wx_download_dir !== undefined) {
        const el = document.getElementById('settingDownloadDir');
        if (el) el.value = config.wx_download_dir;
      }
      if (config.log_level !== undefined) {
        const el = document.getElementById('settingLogLevel');
        if (el) el.value = config.log_level;
      }
      _adsEnabled = config.ads_enabled !== false;
    }
  } catch (e) {
    console.warn("加载配置失败:", e);
  }
  initApp();
}

initConfig();

async function initApp() {
  startLoadingProgress();
  // FAB panel starts closed — user clicks FAB to open

  // 1. 拉全量数据（作者+视频，不需要 Go 服务）
  await loadAllDataFromBackend();

  // 2. 拉一次日志
  refreshLogs();
  startUptimeTimer();

  // 3. 不主动拉服务状态和任务列表 — 等 SSE 连接成功后由 onopen 触发
  //    避免启动时 Go 未就绪产生 503 红色报错
  initSSEListener();

  // 日志轮询（10秒，避免频繁刷日志）
  setInterval(refreshLogs, 10000);

  // 4. 新视频同步轮询（30分钟）- 增量同步，只插入新视频
  syncTimer = setInterval(pollNewVideos, syncInterval);
  // 不在启动时立即调用 pollNewVideos，等 SSE 连接确认 Go 在线后由 onopen 触发

  // 5. 广告开关 + 开屏弹窗
  applyAdsConfig();
}

// ==================== 拉全量数据（调后端 /api/video/all）====================

async function loadAllDataFromBackend() {
  try {
    const res = await fetch("/api/video/all");
    if (!res.ok) return;
    const json = await res.json();
    if (json.code !== 0 || !json.data) return;

    const items = json.data;

    // 1. 映射作者列表
    _allAuthors = items.map(item => mapAuthor(item.author));

    // 2. 写入 State 视频层（替代直接赋值 _authorVideosData）
    for (const item of items) {
      const username = item.author.source_author_id;
      const nickname = item.author.name;
      const videoList = (item.videos || []).map(v => mapVideo(v));
      State.videos.setAuthorVideos(username, videoList, nickname);
    }
    // 同步只读视图
    _authorVideosData = State.videos.allGrouped();

    // 3. 映射目录统计（基于 State 层数据，确保与视频列表一致）
    _catalogData = items.map(item => {
      const username = item.author.source_author_id;
      const authorEntry = _authorVideosData[username];
      const videos = Object.values(authorEntry?.videos || {});
      const total = videos.length;
      const downloaded = videos.filter(v => v.downloaded).length;

      // 按视频类型分类统计
      const shortVideos = videos.filter(v => (v.video_type || 'short_video') === 'short_video');
      const replays = videos.filter(v => v.video_type === 'live_replay');
      const shortVideoDownloaded = shortVideos.filter(v => v.downloaded).length;
      const replayDownloaded = replays.filter(v => v.downloaded).length;

      return {
        username,
        total,
        downloaded,
        pending: total - downloaded,
        progress: total > 0 ? Math.round(downloaded / total * 100) : 0,
        short_video_count: shortVideos.length,
        replay_count: replays.length,
        short_video_downloaded: shortVideoDownloaded,
        replay_downloaded: replayDownloaded,
      };
    });

    // 4. 不在 loadAllDataFromBackend 中拉活跃任务 — 等 SSE 连接成功后由 onopen 触发
    //    避免启动时 Go 未就绪产生 503 红色报错

    // 5. 写入 State 层
    bridgePollUpdate({
      authors: _allAuthors,
      catalog: _catalogData,
      author_videos: _authorVideosData,
      tasks: _activeTasks,
    });

    // 6. UI 更新
    scheduleUIUpdate(updateAuthorGridFromPoll);
  } catch (err) {
    // 静默处理，数据等 SSE 恢复后填充
  }
}

// ==================== 服务状态轮询（轻量）====================

async function pollServiceStatus() {
  try {
    const res = await fetch("/api/service/status");
    const json = await res.json();
    if (json.code !== 0) return;
    const data = json.data;

    updateStatusFromPoll({
      service_online: data.service_online,
      wechat_connected: data.wechat_connected,
      monitor_running: data.monitor_running,
      today_count: data.today_count || 0,
      today_downloaded: data.today_downloaded || 0,
      total_videos: data.total_videos || 0,
    });
  } catch (err) {
    // 服务不可达，静默标记离线
    updateStatusFromPoll({
      service_online: false,
      wechat_connected: false,
      monitor_running: false,
      today_count: 0,
      today_downloaded: 0,
      total_videos: 0,
    });
  }
}

// ==================== 活跃任务刷新（按需）====================

async function refreshActiveTasks() {
  try {
    const res = await fetch("/api/task/list");
    if (!res.ok) {
      // 503 = Go 未就绪，静默返回空，等 SSE onopen 后自动重试
      return;
    }
    const json = await res.json();
    if (json.code !== 0) return;

    const list = json.data?.list || [];

    // 映射后端字段 → 前端格式
    const mapped = list.map(t => ({
      id: t.task_id,
      video_id: t.video_id,
      status: t.status,
      percent: t.progress,
      downloaded: t.downloaded,
      size: t.total_size,
      speed: t.speed,
      title: t.title,
      error_msg: t.error_msg,
    }));

    // 过滤掉已取消的任务（防止竞态：其他 SSE 事件触发的 refresh 把已取消任务又插回来）
    const filtered = (typeof _cancelledTaskIds !== 'undefined' && Object.keys(_cancelledTaskIds).length > 0)
      ? mapped.filter(t => !_cancelledTaskIds[t.id])
      : mapped;

    // State.tasks.setAll 内置 merge 语义（video_id 主键，保留 SSE 实时进度）
    State.tasks.setAll(filtered);
    // 同步只读视图
    _activeTasks = State.tasks.all();

    // 如果所有活跃任务都是 pending 且 Go 在线，说明 resume 还没完成，5s 后重试
    if (_goOnline && _activeTasks.length > 0 && _activeTasks.every(function(t) { return t.status === 'pending' || t.status === 'wait' || t.status === 'paused'; }) && _taskResumeRetryCount < MAX_TASK_RESUME_RETRIES) {
      if (!_taskResumeRetryTimer) {
        _taskResumeRetryTimer = setTimeout(function() {
          _taskResumeRetryTimer = null;
          _taskResumeRetryCount++;
          refreshActiveTasks();
        }, 5000);
      }
    } else if (_taskResumeRetryTimer) {
      clearTimeout(_taskResumeRetryTimer);
      _taskResumeRetryTimer = null;
    }
    // 任务已恢复或不存在，重置重试计数
    if (!_activeTasks.every(function(t) { return t.status === 'pending' || t.status === 'wait' || t.status === 'paused'; })) {
      _taskResumeRetryCount = 0;
    }
  } catch (err) {
    // Go 后端未启动时静默忽略，不弹 toast
  }
}

// ==================== 操作后按需刷新 ====================

async function refreshAfterAuthorChange() {
  await loadAllDataFromBackend();
}

async function refreshAfterVideoChange() {
  await loadAllDataFromBackend();
}

// ==================== 增量同步轮询 ====================

async function pollNewVideos() {
  if (!_goOnline) return;
  try {
    const res = await fetch('/api/video/sync-new', { method: 'POST' });
    if (!res.ok) return;
    const json = await res.json();
    if (json.code !== 0 || !json.data) return;

    const added = json.data.added || 0;
    if (added === 0) return;

    const newVideos = json.data.new_videos || [];
    if (newVideos.length === 0) return;

    // 构建 author_id -> username 映射
    const authorIdMap = {};
    _allAuthors.forEach(a => { authorIdMap[a.id] = a.username; });

    let hasUpdate = false;

    newVideos.forEach(nv => {
      const username = authorIdMap[nv.author_id];
      if (!username) return;
      const authorData = _authorVideosData[username];
      if (!authorData) return;

      if (!authorData.videos[nv.video_id]) {
        // 通过 State 层插入，再同步到 _authorVideosData
        if (State.videos._data[username]) {
          State.videos._data[username].videos[nv.video_id] = mapVideo(nv);
        } else {
          State.videos._data[username] = { nickname: '', videos: { [nv.video_id]: mapVideo(nv) } };
        }
        hasUpdate = true;
      }
    });

    if (!hasUpdate) return;

    // 从 State 同步到 _authorVideosData
    _authorVideosData = State.videos.allGrouped();

    // 更新目录统计
    _catalogData.forEach((cat, idx) => {
      const videos = Object.values(_authorVideosData[cat.username]?.videos || {});
      const total = videos.length;
      const downloaded = videos.filter(v => v.downloaded).length;

      // 按视频类型分类统计
      const shortVideos = videos.filter(v => (v.video_type || 'short_video') === 'short_video');
      const replays = videos.filter(v => v.video_type === 'live_replay');
      const shortVideoDownloaded = shortVideos.filter(v => v.downloaded).length;
      const replayDownloaded = replays.filter(v => v.downloaded).length;

      _catalogData[idx] = {
        ...cat,
        total,
        downloaded,
        pending: total - downloaded,
        progress: total > 0 ? Math.round(downloaded / total * 100) : 0,
        short_video_count: shortVideos.length,
        replay_count: replays.length,
        short_video_downloaded: shortVideoDownloaded,
        replay_downloaded: replayDownloaded,
      };
    });

    // 如果当前在作者详情页，增量插入新视频行
    if (_currentAuthor && _currentPage === 'author') {
      const videos = Object.values(_authorVideosData[_currentAuthor?.username || '']?.videos || {});
      updateVideoListIncremental(videos);
    }

    // 更新作者网格统计
    scheduleUIUpdate(updateAuthorGridFromPoll);

  } catch(err) {
    // 503 = Go/微信未就绪，静默跳过，等 SSE 推送恢复
  }
}

// ==================== 广告开关 ====================

function applyAdsConfig() {
  const adsEls = [
    document.querySelector('.header-contact-btn'),
    ...[...document.querySelectorAll('.settings-section')].filter(el => el.textContent.includes('加入交流群')),
    document.getElementById('qrOverlay'),
  ].filter(Boolean);

  if (!_adsEnabled) {
    return;
  }

  adsEls.forEach(el => el.style.display = '');
  loadSplash();
}
