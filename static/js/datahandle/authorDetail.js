// 作者详情页数据处理

// SSE 监听：实时更新作者下载统计
function initSSEListener() {
  console.log('[SSE] 正在连接 /api/events ...');
  var es = new EventSource('/api/events');

  es.onopen = function() {
    console.log('[SSE] 连接已建立');
    _sseConnected = true;
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
  };

  // 服务状态推送（Go 后端 + 微信客户端）
  es.addEventListener('service_status', function(e) {
    try {
      var data = JSON.parse(e.data);
      console.log('[SSE] 收到 service_status:', data.service_online, data.wechat_connected);
      updateStatusFromPoll({
        service_online: data.service_online,
        wechat_connected: data.wechat_connected,
      });
    } catch(err) {
      console.error('[SSE] service_status 解析失败:', err);
    }
  });

  es.addEventListener('task_completed', function(e) {
    console.log('[SSE] 收到 task_completed 事件:', e.data);
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

  es.onerror = function(err) {
    console.warn('[SSE] 连接错误, readyState:', es.readyState);
    _sseConnected = false;
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
    console.log('[SSE][完成] 作者不在 _catalogData 中: %s', username);
    return;
  }

  var total = data.total;
  var downloaded = data.downloaded;
  var completedVideoId = data.video_id || '';

  console.log('[SSE][完成] 作者统计更新: %s, downloaded %s→%s, total=%s, videoId=%s',
    username, _catalogData[idx].downloaded, downloaded, total, completedVideoId);

  // 1. 更新 _catalogData
  _catalogData[idx] = {
    ..._catalogData[idx],
    downloaded: downloaded,
    pending: total - downloaded,
    progress: total > 0 ? Math.round(downloaded / total * 100) : 0,
  };

  // 2. 更新 _authorVideosData 中该视频的 downloaded 状态
  if (completedVideoId && _authorVideosData[username]) {
    var video = _authorVideosData[username].videos[completedVideoId];
    if (video && !video.downloaded) {
      _authorVideosData[username].videos[completedVideoId] = {
        ...video,
        downloaded: true,
        download_path: data.download_path || video.download_path || '',
      };
      console.log('[SSE][完成] 已更新 _authorVideosData: %s downloaded=true, path=%s', completedVideoId, data.download_path || '');

      // [新增] 使用 State 层更新状态（触发 ReactiveRenderer）
      if (typeof State !== 'undefined' && State.videos && State.videos.updateStatus) {
        State.videos.updateStatus(completedVideoId, {
          downloaded: true,
          download_path: data.download_path || ''
        });
      }
    }
  }

  // 3. 更新作者卡片统计
  updateAuthorCardStats(username, _catalogData[idx]);

  // 4. 如果在详情页，更新头部统计 + 单个视频行渲染
  if (_currentAuthor && _currentAuthor.username === username && _currentPage === 'author') {
    // 已下载显示 X/Y 格式：需要同时获取当前类型的总数
    var catEntry = _catalogData.find(function(c) { return c.username === username; });
    if (catEntry) {
      var isReplay = _currentVideoType === 'live_replay';
      var typeTotal = isReplay ? (catEntry.replay_count || 0) : (catEntry.short_video_count || 0);
      var typeDownloaded = isReplay ? (catEntry.replay_downloaded || 0) : (catEntry.short_video_downloaded || 0);
      document.getElementById("authorDownloaded").textContent = typeDownloaded + '/' + typeTotal;
    }
    document.getElementById("authorPending").textContent = total - downloaded;
    document.getElementById("authorTotal").textContent = total;

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
    console.log('[SSE][数据层] 忽略已取消任务的残留消息: taskId=%s, status=%s', taskId, data.status);
    return;
  }

  // 通过 _activeTasks 的 task_id → video_id 映射获取正确的 videoId
  // SSE 消息中的 video_id 可能为空（Go后端直播回放缺少 labels.id），不能直接用
  var existingTask = _activeTasks.find(function(t) { return t.id === taskId; });
  var videoId = existingTask ? existingTask.video_id : (data.video_id || '');
  if (!videoId) return;

  console.log('[SSE][数据层] 收到进度: videoId=%s, taskId=%s, status=%s, downloaded=%s, speed=%s, total_size=%s',
    videoId, data.id, data.status, data.downloaded, data.speed, data.total_size);

  // 完成/错误 → 全量刷新 + 更新视频行UI
  if (data.status === 'done' || data.status === 'error') {
    console.log('[SSE][数据层] 任务终态: videoId=%s, status=%s → 触发 refreshActiveTasks + 更新视频行', videoId, data.status);

    // 0. 清除该 videoId 的节流定时器，防止延迟的进度更新覆盖终态 UI
    if (_progressThrottleTimers[videoId]) {
      clearTimeout(_progressThrottleTimers[videoId]);
      _progressThrottleTimers[videoId] = null;
      console.log('[SSE][数据层] 终态清除节流器: videoId=%s', videoId);
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
          if (!video.downloaded) {
            videos[videoId] = { ...video, downloaded: true, download_path: data.download_path || video.download_path || '' };
            console.log('[SSE][数据层] 标记视频已下载: videoId=%s, username=%s, path=%s', videoId, username, data.download_path || '');

            // [新增] 使用 State 层更新状态（触发 ReactiveRenderer）
            if (typeof State !== 'undefined' && State.videos && State.videos.updateStatus) {
              State.videos.updateStatus(videoId, {
                downloaded: true,
                download_path: data.download_path || ''
              });
            }
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

    // 3. 刷新任务列表
    refreshActiveTasks();

    // 4. 异步全量刷新数据（获取 download_path 等完整信息），刷新后补全播放按钮
    var _completedVideoId = (data.status === 'done') ? videoId : null;
    loadAllDataFromBackend().then(function() {
      if (_completedVideoId && _currentAuthor && _currentPage === 'author') {
        var refreshedVideo = _authorVideosData[_currentAuthor.username]?.videos[_completedVideoId];
        if (refreshedVideo && refreshedVideo.download_path && typeof updateSingleVideoCompleted === 'function') {
          console.log('[SSE][数据层] 全量刷新后补全播放按钮: videoId=%s, path=%s', _completedVideoId, refreshedVideo.download_path);
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
    console.log('[SSE][数据层] 新任务插入 _activeTasks: videoId=%s, taskId=%s, %s%%', videoId, taskId, pct);
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

    // 进度合理性检查：防止异常跳跃（非完成状态下，进度跳跃超过 50% 视为异常）
    // 如果新进度远大于旧进度，且状态不是 done/completed，可能是 Go 后端返回了错误数据
    if (pct > oldPct + 50 && data.status !== 'done' && data.status !== 'completed' && data.status !== 'error') {
      console.warn('[SSE][数据层] 进度跳跃异常: videoId=%s, taskId=%s, 旧进度=%s%%, 新进度=%s%%, status=%s → 忽略此更新',
        videoId, data.id, oldPct, pct, data.status);
      return;  // 忽略异常的进度更新
    }

    _activeTasks[taskIdx] = {
      ..._activeTasks[taskIdx],
      downloaded: rawDownloaded,
      size: rawSize,
      speed: rawSpeed,
      percent: pct,
      status: data.status,
    };

    console.log('[SSE][数据层] 更新 _activeTasks: videoId=%s, %s%%→%s%%, downloaded=%s/%s, speed=%s/s, 节流=%s',
      videoId, oldPct, pct, formatFileSize(rawDownloaded), formatFileSize(rawSize), formatFileSize(rawSpeed),
      _progressThrottleTimers[videoId] ? '跳过' : '放行');
  }

  // 200ms 节流：防止高频 DOM 更新
  if (_progressThrottleTimers[videoId]) return;
  _progressThrottleTimers[videoId] = setTimeout(function() {
    _progressThrottleTimers[videoId] = null;
    // 防御：任务可能已在终态处理中被移除，跳过过期的进度更新
    var currentTask = _activeTasks.find(function(t) { return t.video_id === videoId; });
    if (!currentTask) {
      console.log('[SSE][数据层] 节流回调跳过: videoId=%s 已不在 _activeTasks 中', videoId);
      return;
    }
    if (typeof updateSingleVideoProgress === 'function') {
      updateSingleVideoProgress(videoId, currentTask);
    }
  }, 200);
}

function updateAuthorCardStats(username, cat) {
  var isListView = _currentView === 'list';
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
  _currentVideoType = 'short_video'; // 重置为默认类型

  // 重置视频类型 Tab UI
  document.querySelectorAll('.video-type-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.type === 'short_video');
  });

  // [新增] 通知 ReactiveRenderer 当前视图状态
  if (typeof ReactiveRenderer !== 'undefined') {
    ReactiveRenderer.setCurrentView('all', 'short_video', { username: username });
  }

  console.log(`[DEBUG][loadAuthorDetail] ===== 进入作者详情 =====`);
  console.log(`[DEBUG][loadAuthorDetail] username=${username}, goOnline=${_goOnline}`);

  // 更新头部信息
  const author = _allAuthors.find(a => a.username === username);
  const cat = _catalogData.find(c => c.username === username) || {};

  console.log(`[DEBUG][loadAuthorDetail] _catalogData中的统计: total=${cat.total}, downloaded=${cat.downloaded}, pending=${cat.pending}`);
  console.log(`[DEBUG][loadAuthorDetail] 短视频=${cat.short_video_count}, 回放=${cat.replay_count}`);

  // 先看 _authorVideosData 中该作者的视频 downloaded 状态
  const localVideosBefore = Object.values(_authorVideosData[username]?.videos || {});
  const localDownloaded = localVideosBefore.filter(v => v.downloaded).length;
  const localPending = localVideosBefore.filter(v => !v.downloaded).length;
  console.log(`[DEBUG][loadAuthorDetail] _authorVideosData视频统计: 总数=${localVideosBefore.length}, downloaded=${localDownloaded}, pending=${localPending}`);

  // 打印前5个视频的 downloaded 状态
  localVideosBefore.slice(0, 5).forEach(v => {
    console.log(`[DEBUG][loadAuthorDetail] 视频: id=${v.id}, title=${v.title?.slice(0,15)}, downloaded=${v.downloaded}, download_path=${v.download_path}`);
  });

  // 头像
  const initial = (author?.nickname || '?')[0];
  document.getElementById("authorAvatar").innerHTML = author?.head_url
    ? `<img src="${author.head_url}" onerror="this.style.display='none'">`
    : `<span style="font-size:24px;font-weight:600;color:var(--text-secondary)">${initial}</span>`;

  document.getElementById("authorName").textContent = author?.nickname || '未知';

  console.log(`[DEBUG][loadAuthorDetail] 头部渲染: total=${cat.total || 0}, downloaded=${cat.downloaded || 0}, pending=${cat.pending || 0}`);

  // 更新头部统计（使用 _catalogData 中的分类统计）
  updateAuthorStatsByType({
    short_video_count: cat.short_video_count || 0,
    replay_count: cat.replay_count || 0,
    short_video_downloaded: cat.short_video_downloaded || 0,
    replay_downloaded: cat.replay_downloaded || 0,
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
    console.log(`[DEBUG][loadAuthorDetail] 用本地数据渲染了 ${localVideos.length} 个视频`);
  } else {
    document.getElementById("videoList").innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-tertiary)">加载中...</div>';
    console.log(`[DEBUG][loadAuthorDetail] 本地无视频数据，显示加载中`);
  }

  // 如果 Go 在线，增量同步作者视频
  if (_goOnline && author?.id) {
    try {
      console.log(`[DEBUG][loadAuthorDetail] 开始增量同步: author.id=${author.id}`);
      const res = await fetch(`/api/video/author/${author.id}/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        console.log(`[DEBUG][loadAuthorDetail] 增量同步请求失败: ${res.status}`);
      } else {
        const data = await res.json();
        console.log(`[DEBUG][loadAuthorDetail] 增量同步返回: code=${data.code}, added=${data.data?.added || 0}`);

        if (data.code === 0 && (data.data?.added || 0) > 0) {
          const added = data.data.added;
          console.log(`[DEBUG][loadAuthorDetail] 有新增视频(${added})，执行 loadAllDataFromBackend`);
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
            console.log(`[DEBUG][loadAuthorDetail] 全量刷新后: 总数=${newVideos.length}, downloaded=${newDownloaded}`);
            renderVideoList(newVideos);
            updateAuthorStatsByType(typeData.stats);
            // 更新全局进度条
            if (typeof updateAuthorGlobalProgress === 'function') {
              updateAuthorGlobalProgress();
            }
          }
        } else {
          console.log(`[DEBUG][loadAuthorDetail] 无新增视频，不刷新`);
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
  console.log(`[DEBUG][loadAuthorDetail] ===== 最终DOM统计: shortVideo=${finalShortVideo}, replay=${finalReplay}, downloaded=${finalDownloaded} =====`);
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
      console.log(`[增量同步] ${username}: 新增 ${data.data?.added || 0} 个视频`);
    }
  } catch(e) {
    console.error('[增量同步] 失败:', e);
  }
}
