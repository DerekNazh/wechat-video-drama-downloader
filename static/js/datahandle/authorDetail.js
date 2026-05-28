// 作者详情页数据处理

// SSE 监听：实时更新作者下载统计
function initSSEListener() {
  var es = new EventSource('/api/events');

  es.onopen = function() {
    _sseConnected = true;
    // 隐藏 SSE 断连提示
    var sseBanner = document.getElementById('sse-status-banner');
    if (sseBanner) sseBanner.style.display = 'none';
    // SSE 重连后，主动请求一次当前状态（避免缓存错误）
    fetch("/api/service/status")
      .then(r => r.json())
      .then(s => {
        if (s.code === 0) {
          updateStatusFromPoll({
            service_online: s.data.service_online,
            wechat_connected: s.data.wechat_connected,
            monitor_running: s.data.monitor_running,
            today_count: s.data.today_count || 0,
            today_downloaded: s.data.today_downloaded || 0,
            total_videos: s.data.total_videos || 0,
          });
        }
      })
      .catch(() => {});
    // SSE 重连后，刷新活跃任务列表（防止瞬断期间任务状态不同步）
    if (typeof refreshActiveTasks === 'function') refreshActiveTasks();
  };

  // 服务状态推送（Go 后端 + 微信客户端）
  es.addEventListener('service_status', function(e) {
    try {
      var data = JSON.parse(e.data);
      updateStatusFromPoll({
        service_online: data.service_online,
        wechat_connected: data.wechat_connected,
      });
    } catch(err) {
      console.error('[SSE] service_status 解析失败:', err);
    }
  });

  es.addEventListener('task_completed', function(e) {
    try {
      var data = JSON.parse(e.data);
      handleSSETaskCompleted(data);
    } catch(err) {
      console.error('[SSE] 解析失败:', err);
    }
  });

  es.addEventListener('task_progress', function(e) {
    try {
      var data = JSON.parse(e.data);
      // error 状态时记录日志
      if (data.status === 'error') {
        console.warn('[SSE] task_progress error: id=%s, video_id=%s, error=%s', data.id, data.video_id, data.error || '');
      }
      handleSSETaskProgress(data);
    } catch(err) {
      console.error('[SSE] task_progress 解析失败:', err);
    }
  });

  es.addEventListener('import_progress', function(e) {
    try {
      var data = JSON.parse(e.data);
      // 文档监控事件由 DocSyncMonitor 处理
      if (data.import_type === 'doc_sync') {
        if (typeof DocSyncMonitor !== 'undefined') {
          DocSyncMonitor.handleSSEProgress(data);
        }
        return;
      }
      // 其他导入事件由 ImportModal 处理
      if (typeof ImportModal !== 'undefined') {
        ImportModal.handleSSEProgress(data);
      }
    } catch(err) {
      console.error('[SSE] import_progress 解析失败:', err);
    }
  });

  es.addEventListener('video_fetch_progress', function(e) {
    try {
      var data = JSON.parse(e.data);
      handleSSEVideoFetchProgress(data);
    } catch(err) {
      console.error('[SSE] video_fetch_progress 解析失败:', err);
    }
  });

  es.addEventListener('tasks_resumed', function(e) {
    try {
      var data = JSON.parse(e.data);
      var resumed = data.resumed || data.count || 0;
      var failed = data.failed || 0;
      if (resumed > 0) {
        // 暂停徽章 → 恢复中（过渡动画）
        document.querySelectorAll('.video-status-badge.paused').forEach(function(badge) {
          badge.className = 'video-status-badge resuming';
          var pctEl = badge.querySelector('.progress-percent');
          var pct = pctEl ? pctEl.textContent.replace('%', '').trim() : '0';
          badge.innerHTML = '恢复中 (' + pct + '%)';
          badge.title = '正在恢复下载...';
          // 3s fallback: 如果进度 SSE 没来，强制刷新回 downloading
          setTimeout(function() {
            if (badge.classList.contains('resuming')) {
              if (typeof refreshActiveTasks === 'function') refreshActiveTasks();
            }
          }, 3000);
        });
        // 显示 toast（含失败数）
        if (typeof showToast === 'function') {
          var msg = '已恢复 ' + resumed + ' 个下载任务';
          if (failed > 0) msg += '，' + failed + ' 个恢复失败';
          showToast({ type: failed > 0 ? 'warning' : 'success', title: '断点续传', message: msg });
        }
        // 刷新活跃任务列表
        if (typeof refreshActiveTasks === 'function') refreshActiveTasks();
      }
    } catch(err) {
      console.error('[SSE] tasks_resumed 解析失败:', err);
    }
  });

  es.addEventListener('delete_author_progress', function(e) {
    try {
      var data = JSON.parse(e.data);
      if (typeof handleDeleteAuthorSSEProgress === 'function') {
        handleDeleteAuthorSSEProgress(data);
      }
    } catch(err) {
      console.error('[SSE] delete_author_progress 解析失败:', err);
    }
  });

  es.onerror = function(err) {
    console.warn('[SSE] 连接错误, readyState:', es.readyState);
    _sseConnected = false;
    // 显示 SSE 断连提示
    var sseBanner = document.getElementById('sse-status-banner');
    if (sseBanner) sseBanner.style.display = 'flex';
    // SSE 断开时显示离线（重连后会自动恢复）
    updateStatusFromPoll({
      service_online: false,
      wechat_connected: false,
    });
  };
}

function handleSSETaskCompleted(data) {
  var username = data.username;
  if (!username) return;

  var idx = _catalogData.findIndex(function(c) { return c.username === username; });
  if (idx < 0) {
    return;
  }

  var total = data.total;
  var downloaded = data.downloaded;
  var completedVideoId = data.video_id || '';


  // 1. 先更新 _authorVideosData 中该视频的 downloaded 状态
  if (completedVideoId && _authorVideosData[username]) {
    var video = _authorVideosData[username].videos[completedVideoId];
    if (video && !video.downloaded) {
      _authorVideosData[username].videos[completedVideoId] = {
        ...video,
        downloaded: true,
        download_path: data.download_path || video.download_path || '',
      };

      // 使用 State 层更新状态（触发 ReactiveRenderer）
      if (typeof State !== 'undefined' && State.videos && State.videos.updateStatus) {
        State.videos.updateStatus(completedVideoId, {
          downloaded: true,
          download_path: data.download_path || ''
        });
      }
    }
  }

  // 2. 从 _authorVideosData 重新计算分类统计（确保 short_video_downloaded 等字段与视频列表一致）
  var allVideos = Object.values(_authorVideosData[username]?.videos || {});
  var shortVideos = allVideos.filter(function(v) { return (v.video_type || 'short_video') === 'short_video'; });
  var replays = allVideos.filter(function(v) { return v.video_type === 'live_replay'; });
  var svDownloaded = shortVideos.filter(function(v) { return v.downloaded; }).length;
  var rpDownloaded = replays.filter(function(v) { return v.downloaded; }).length;

  _catalogData[idx] = {
    ..._catalogData[idx],
    downloaded: downloaded,
    pending: total - downloaded,
    progress: total > 0 ? Math.round(downloaded / total * 100) : 0,
    short_video_count: shortVideos.length,
    replay_count: replays.length,
    short_video_downloaded: svDownloaded,
    replay_downloaded: rpDownloaded,
  };

  // 3. 更新作者卡片统计
  updateAuthorCardStats(username, _catalogData[idx]);

  // 4. 如果在详情页，更新头部统计 + 单个视频行渲染
  if (_currentAuthor && _currentAuthor.username === username && _currentPage === 'author') {
    // 使用已有的 updateAuthorStatsByType 更新统计（避免引用不存在的 DOM 元素）
    var catEntry = _catalogData.find(function(c) { return c.username === username; });
    if (catEntry) {
      updateAuthorStatsByType({
        short_video_count: catEntry.short_video_count || 0,
        replay_count: catEntry.replay_count || 0,
        short_video_downloaded: catEntry.short_video_downloaded || 0,
        replay_downloaded: catEntry.replay_downloaded || 0,
      });
    }

    // 把完成的视频行从"下载中"切换为"已下载"
    if (completedVideoId && typeof updateSingleVideoCompleted === 'function') {
      var completedVideo = _authorVideosData[username]?.videos[completedVideoId];
      if (completedVideo) {
        updateSingleVideoCompleted(completedVideoId, completedVideo);
      }
    }
  }

  // 5. 从 _activeTasks 移除已完成任务
  _activeTasks = _activeTasks.filter(function(t) { return t.video_id !== completedVideoId; });
  State.tasks.setAll(_activeTasks);

  // 5.1 清除该视频的节流定时器，防止延迟的进度更新覆盖终态 UI
  if (_progressThrottleTimers[completedVideoId]) {
    clearTimeout(_progressThrottleTimers[completedVideoId]);
    _progressThrottleTimers[completedVideoId] = null;
  }

  // 6. 更新全局统计
  if (data.today_count !== undefined) {
    updateStatusFromPoll({
      today_count: data.today_count,
      today_downloaded: data.today_downloaded,
      total_videos: data.total_videos,
    });
  }
}

// SSE 实时进度节流
var _progressThrottleTimers = {};

// 已取消的任务ID集合（防止 SSE 残留消息把已取消的任务又插回 _activeTasks）
var _cancelledTaskIds = {};

function handleSSETaskProgress(data) {
  var taskId = data.id;
  if (!taskId) return;

  // 忽略已取消任务的残留进度消息
  if (taskId && _cancelledTaskIds[taskId]) {
    // 如果收到终态（done/error），清除取消标记
    if (data.status === 'done' || data.status === 'error') {
      delete _cancelledTaskIds[taskId];
    }
    return;
  }

  // 通过 _activeTasks 的 task_id → video_id 映射获取正确的 videoId
  // SSE 消息中的 video_id 可能为空（Go后端直播回放缺少 labels.id），不能直接用
  var existingTask = _activeTasks.find(function(t) { return t.id === taskId; });
  var videoId = existingTask ? existingTask.video_id : (data.video_id || '');
  if (!videoId) return;


  // 完成/错误 → 全量刷新 + 更新视频行UI
  if (data.status === 'done' || data.status === 'error') {

    // 0. 清除该 videoId 的节流定时器，防止延迟的进度更新覆盖终态 UI
    if (_progressThrottleTimers[videoId]) {
      clearTimeout(_progressThrottleTimers[videoId]);
      _progressThrottleTimers[videoId] = null;
    }

    // 1. 从 _activeTasks 移除已完成任务（使用 taskId 精确匹配，避免误删其他任务）
    var taskId = data.id;
    _activeTasks = _activeTasks.filter(function(t) { return t.id !== taskId; });
    State.tasks.setAll(_activeTasks);

    // 2. 标记视频为已下载 + 更新视频行UI
    if (data.status === 'done' && videoId) {
      // 在 _authorVideosData 中查找并更新该视频
      for (var username in _authorVideosData) {
        var videos = _authorVideosData[username].videos;
        if (videos && videos[videoId]) {
          var video = videos[videoId];
          // 守卫：task_completed 可能已先处理过，跳过重复更新
          if (video.downloaded) {
            break;
          }
          videos[videoId] = { ...video, downloaded: true, download_path: data.download_path || video.download_path || '' };

          // [新增] 使用 State 层更新状态（触发 ReactiveRenderer）
          if (typeof State !== 'undefined' && State.videos && State.videos.updateStatus) {
            State.videos.updateStatus(videoId, {
              downloaded: true,
              download_path: data.download_path || ''
            });
          }
          // 更新视频行UI（隐藏下载框，显示"已下载"）
          if (typeof updateSingleVideoCompleted === 'function') {
            updateSingleVideoCompleted(videoId, videos[videoId]);
          }
          break;
        }
      }
    } else if (data.status === 'error' && videoId) {
      // 错误状态：恢复视频行为"待下载"
      console.warn('[SSE][数据层][DEBUG] 任务错误详情: videoId=%s, taskId=%s, error_msg="%s", downloaded=%s, speed=%s, total_size=%s',
        videoId, data.id, data.error_msg || '', data.downloaded, data.speed, data.total_size);
      if (typeof updateSingleVideoError === 'function') {
        updateSingleVideoError(videoId);
      }
    }

    // 2.5 终态时主动清除取消标记（防止 TTL 过期后残留消息重新插入）
    if (typeof _cancelledTaskIds !== 'undefined' && _cancelledTaskIds[data.id]) {
      delete _cancelledTaskIds[data.id];
    }

    // 3. 刷新任务列表
    refreshActiveTasks();

    // 4. 异步全量刷新数据（获取 download_path 等完整信息），刷新后补全播放按钮
    var _completedVideoId = (data.status === 'done') ? videoId : null;
    loadAllDataFromBackend().then(function() {
      if (_completedVideoId && _currentAuthor && _currentPage === 'author') {
        var refreshedVideo = _authorVideosData[_currentAuthor.username]?.videos[_completedVideoId];
        if (refreshedVideo && refreshedVideo.download_path && typeof updateSingleVideoCompleted === 'function') {
          updateSingleVideoCompleted(_completedVideoId, refreshedVideo);
        }
      }
    });
    return;
  }

  var rawDownloaded = data.downloaded || 0;
  var rawSize = data.total_size || 0;
  var rawSpeed = data.speed || 0;
  var pct = rawSize > 0 ? Math.round(rawDownloaded / rawSize * 100) : 0;

  // 查找 _activeTasks 中的进度（优先 task_id 精确匹配，确保任务隔离）
  var taskIdx = _activeTasks.findIndex(function(t) { return t.id === taskId; });
  if (taskIdx < 0 && videoId) {
    taskIdx = _activeTasks.findIndex(function(t) { return t.video_id === videoId; });
  }

  if (taskIdx < 0) {
    _activeTasks.push({
      id: taskId,
      video_id: videoId,  // 使用从 _activeTasks 映射或 data.video_id 获取的正确 videoId
      status: data.status,
      percent: pct,
      downloaded: rawDownloaded,
      size: rawSize,
      speed: rawSpeed,
    });
    State.tasks.setAll(_activeTasks);
    taskIdx = _activeTasks.length - 1;
  } else {
    var oldPct = _activeTasks[taskIdx].percent;
    var oldStatus = _activeTasks[taskIdx].status;

    // 进度合理性检查：基于时间的变化率，防止后端返回错误数据
    // 断点续传后进度可能合法跳跃，因此只在短时间跳跃过大时才视为异常
    var now = Date.now();
    var lastUpdate = _activeTasks[taskIdx]._lastUpdateTime || 0;
    var elapsed = (now - lastUpdate) / 1000;
    var maxJumpPerSecond = 30;
    var maxJump = Math.max(50, maxJumpPerSecond * Math.max(elapsed, 1));
    if (pct > oldPct + maxJump && data.status !== 'done' && data.status !== 'completed' && data.status !== 'error') {
      console.warn('[SSE][数据层] 进度跳跃异常: videoId=%s, taskId=%s, 旧进度=%s%%, 新进度=%s%%, 间隔=%ss, 阈值=%s%%, status=%s → 忽略此更新',
        videoId, data.id, oldPct, pct, elapsed.toFixed(1), maxJump, data.status);
      return;
    }

    _activeTasks[taskIdx] = {
      ..._activeTasks[taskIdx],
      downloaded: rawDownloaded,
      size: rawSize,
      speed: rawSpeed,
      percent: pct,
      status: data.status,
      _lastUpdateTime: now,
    };

  }

  // 200ms 节流：防止高频 DOM 更新
  if (_progressThrottleTimers[videoId]) return;
  _progressThrottleTimers[videoId] = setTimeout(function() {
    _progressThrottleTimers[videoId] = null;
    // 防御：任务可能已在终态处理中被移除，跳过过期的进度更新
    var currentTask = _activeTasks.find(function(t) { return t.video_id === videoId; });
    if (!currentTask) {
      return;
    }
    if (typeof updateSingleVideoProgress === 'function') {
      updateSingleVideoProgress(videoId, currentTask);
    }
  }, 200);
}

function handleSSEVideoFetchProgress(data) {
  var progressCountEl = document.getElementById('syncProgressCount');
  if (!progressCountEl) return;

  if (data.phase === 'done') {
    progressCountEl.textContent = '已获取 ' + data.current + ' 个视频';
  } else {
    progressCountEl.textContent = '已获取 ' + data.current + ' / ' + data.total + ' 个视频';
  }
}

function updateAuthorCardStats(username, cat) {
  var isListView = State.ui.getAuthorViewMode() === 'list';
  var el = isListView
    ? document.querySelector('.author-list-item[data-username="' + username + '"]')
    : document.querySelector('.author-card[onclick*="' + username + '"]');
  if (!el) return;

  // 使用分类统计字段
  var shortVideoCount = cat.short_video_count || 0;
  var replayCount = cat.replay_count || 0;
  var shortVideoDownloaded = cat.short_video_downloaded || 0;
  var replayDownloaded = cat.replay_downloaded || 0;
  var total = shortVideoCount + replayCount;
  var downloaded = shortVideoDownloaded + replayDownloaded;
  var pending = cat.pending || 0;
  var progress = cat.progress || 0;

  if (isListView) {
    // 列表视图：更新 .author-list-stats .num
    var nums = el.querySelectorAll('.author-list-stats .num');
    // 格式：短视频 已下载/总数 · 回放 已下载/总数
    if (nums[0]) nums[0].textContent = `${shortVideoDownloaded}/${shortVideoCount}`;
    if (nums[1]) nums[1].textContent = `${replayDownloaded}/${replayCount}`;
    var progressFill = el.querySelector('.author-list-progress-fill');
    if (progressFill) progressFill.style.width = progress + '%';
    var percent = el.querySelector('.author-list-percent');
    if (percent) percent.textContent = progress + '%';
  } else {
    // 卡片视图：更新 .stat-item .value
    var statItems = el.querySelectorAll('.stat-item .value');
    // 格式：短视频 已下载/总数，回放 已下载/总数
    if (statItems[0]) statItems[0].textContent = `${shortVideoDownloaded}/${shortVideoCount}`;
    if (statItems[1]) statItems[1].textContent = `${replayDownloaded}/${replayCount}`;
    var progressFill = el.querySelector('.author-progress-fill');
    if (progressFill) progressFill.style.width = progress + '%';
    var progressText = el.querySelector('.author-progress-text');
    if (progressText) progressText.textContent = progress + '% 完成';
  }
}

// 更新作者详情页统计（从后端返回的类型统计数据更新）
function updateAuthorStats(data) {
  const username = _currentAuthor?.username;
  if (!username) return;

  // 从后端响应获取统计，支持两种格式：
  // 1. 传入 data 为 { videos: [...], short_video_count, replay_count, short_video_downloaded, replay_downloaded }
  // 2. 传入 data 为 videos 数组（兼容旧调用）
  let shortVideoCount = 0;
  let replayCount = 0;
  let downloaded = 0;

  if (Array.isArray(data)) {
    // 兼容旧调用：从视频数组计算
    shortVideoCount = data.filter(v => (v.video_type || 'short_video') === 'short_video').length;
    replayCount = data.filter(v => v.video_type === 'live_replay').length;
    downloaded = data.filter(v => v.downloaded).length;
  } else if (data && typeof data === 'object') {
    // 新格式：从后端响应获取
    shortVideoCount = data.short_video_count || 0;
    replayCount = data.replay_count || 0;
    // downloaded 根据当前类型显示
    if (_currentVideoType === 'live_replay') {
      downloaded = data.replay_downloaded || 0;
    } else {
      downloaded = data.short_video_downloaded || 0;
    }
  }

  const shortVideoEl = document.getElementById("authorShortVideo");
  const replayEl = document.getElementById("authorReplay");
  const downloadedEl = document.getElementById("authorDownloaded");

  if (shortVideoEl) shortVideoEl.textContent = shortVideoCount;
  if (replayEl) replayEl.textContent = replayCount;
  if (downloadedEl) downloadedEl.textContent = downloaded;
}

// 加载作者详情
async function loadAuthorDetail(username) {
  _currentPageNum = 1;
  _currentVideoType = 'short_video';

  // 清空选中状态
  if (typeof clearSelection === 'function') clearSelection();

  // 清空搜索和日期过滤
  var searchInput = document.getElementById('videoSearchInput');
  if (searchInput) searchInput.value = '';
  if (typeof _dateRange !== 'undefined') _dateRange = { start: null, end: null };
  var dateLabel = document.getElementById('dateFilterLabel');
  if (dateLabel) dateLabel.textContent = '全部日期';

  // 重置视频类型 Tab UI
  document.querySelectorAll('.video-type-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.type === 'short_video');
  });

  // 重置下载状态过滤 Tab 到"全部"
  document.querySelectorAll('.video-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === 'all');
  });

  // [新增] 通知 ReactiveRenderer 当前视图状态
  if (typeof ReactiveRenderer !== 'undefined') {
    ReactiveRenderer.setCurrentView('all', 'short_video', { username: username });
  }


  // 更新头部信息
  const author = _allAuthors.find(a => a.username === username);
  const cat = _catalogData.find(c => c.username === username) || {};


  // 先看 _authorVideosData 中该作者的视频 downloaded 状态
  const localVideosBefore = Object.values(_authorVideosData[username]?.videos || {});
  const localDownloaded = localVideosBefore.filter(v => v.downloaded).length;
  const localPending = localVideosBefore.filter(v => !v.downloaded).length;

  // 打印前5个视频的 downloaded 状态
  localVideosBefore.slice(0, 5).forEach(v => {
  });

  // 头像
  const initial = (author?.nickname || '?')[0];
  document.getElementById("authorAvatar").innerHTML = author?.head_url
    ? `<img src="${author.head_url}" onerror="this.style.display='none'">`
    : `<span style="font-size:24px;font-weight:600;color:var(--text-secondary)">${initial}</span>`;

  document.getElementById("authorName").textContent = author?.nickname || '未知';


  // 更新头部统计（从 _authorVideosData 实时计算，不依赖可能过时的 _catalogData）
  const detailVideos = Object.values(_authorVideosData[username]?.videos || {});
  const detailSV = detailVideos.filter(v => (v.video_type || 'short_video') === 'short_video');
  const detailRP = detailVideos.filter(v => v.video_type === 'live_replay');
  updateAuthorStatsByType({
    short_video_count: detailSV.length,
    replay_count: detailRP.length,
    short_video_downloaded: detailSV.filter(v => v.downloaded).length,
    replay_downloaded: detailRP.filter(v => v.downloaded).length,
  });
  // 更新全局进度条
  if (typeof updateAuthorGlobalProgress === 'function') {
    updateAuthorGlobalProgress();
  }
  // 触发 Tab 数量标注更新
  if (typeof ReactiveRenderer !== 'undefined' && ReactiveRenderer._updateTabLabels) {
    var stats = State.videos.getStatsByType(username);
    if (stats) ReactiveRenderer._updateTabLabels(stats);
  }

  // 先用本地数据渲染视频列表（避免闪烁）
  const localVideos = Object.values(_authorVideosData[username]?.videos || {});
  if (localVideos.length > 0) {
    renderVideoList(localVideos);
  } else {
    document.getElementById("videoList").innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-tertiary)">加载中...</div>';
  }

  // 如果 Go 在线，增量同步作者视频
  if (_goOnline && author?.id) {
    try {
      const res = await fetch(`/api/video/author/${author.id}/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
      } else {
        const data = await res.json();

        if (data.code === 0 && (data.data?.added || 0) > 0) {
          const added = data.data.added;
          await loadAllDataFromBackend();
          // 重新加载当前类型的视频
          const typeRes = await fetch(`/api/video/author/${author.id}?video_type=${_currentVideoType}`);
          const typeData = await typeRes.json();
          if (typeData.code === 0 && Array.isArray(typeData.data)) {
            _authorVideosData[username] = { videos: {} };
            typeData.data.forEach(v => {
              const mapped = mapVideo(v);
              _authorVideosData[username].videos[v.video_id] = mapped;
            });
            const newVideos = Object.values(_authorVideosData[username].videos);
            const newDownloaded = newVideos.filter(v => v.downloaded).length;
            renderVideoList(newVideos);
            updateAuthorStatsByType(typeData.stats);
            // 更新全局进度条
            if (typeof updateAuthorGlobalProgress === 'function') {
              updateAuthorGlobalProgress();
            }
          }
        } else {
          // 本地本来就没视频时，显示空状态而非"加载中..."
          if (localVideos.length === 0) {
            renderVideoList([]);
          }
        }
      }
    } catch(e) {
      console.error('[DEBUG][loadAuthorDetail] 增量同步失败:', e);
    }
  } else {
    // Go 不在线且本地无视频，显示空状态
    if (localVideos.length === 0) {
      renderVideoList([]);
    }
  }

  // 最终渲染后的统计
  const finalShortVideo = document.getElementById("authorShortVideo")?.textContent;
  const finalReplay = document.getElementById("authorReplay")?.textContent;
  const finalDownloaded = document.getElementById("authorDownloaded")?.textContent;
}

// 增量同步作者视频
async function syncAuthorVideos(username) {
  const author = _allAuthors.find(a => a.username === username);
  if (!author?.id) return;
  try {
    const res = await apiFetch(`/api/video/author/${author.id}/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await res.json();
    if (data.code === 0) {
    }
  } catch(e) {
    console.error('[增量同步] 失败:', e);
  }
}
