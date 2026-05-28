// 视频列表渲染组件

function escapeAttr(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// 当前视频类型：short_video | live_replay
var _currentVideoType = 'short_video';

// 切换视频类型（一级 Tab）
async function switchVideoType(type) {
  console.log(`[switchVideoType] 开始切换，type=${type}, 当前类型=${_currentVideoType}`);

  if (_currentVideoType === type) {
    console.log(`[switchVideoType] 类型相同，跳过切换`);
    return;
  }
  _currentVideoType = type;
  console.log(`[switchVideoType] 已更新 _currentVideoType=${_currentVideoType}`);

  // 更新 Tab 样式
  document.querySelectorAll('.video-type-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.type === type);
  });
  console.log(`[switchVideoType] 已更新 Tab 样式`);

  // 重置分页、清空选中
  _currentPageNum = 1;
  if (typeof clearSelection === 'function') clearSelection();

  // 清空搜索和日期过滤
  var searchInput = document.getElementById('videoSearchInput');
  if (searchInput) searchInput.value = '';
  if (typeof _dateRange !== 'undefined') _dateRange = { start: null, end: null };
  var dateLabel = document.getElementById('dateFilterLabel');
  if (dateLabel) dateLabel.textContent = '全部日期';

  // [新增] 通知 ReactiveRenderer 当前视图状态
  if (typeof ReactiveRenderer !== 'undefined') {
    ReactiveRenderer.setCurrentView('all', type, _currentAuthor);
  }

  // 重新从后端加载对应类型的视频列表
  console.log(`[switchVideoType] _currentAuthor=`, _currentAuthor);
  if (_currentAuthor?.id) {
    try {
      const url = `/api/video/author/${_currentAuthor.id}?video_type=${type}`;
      console.log(`[switchVideoType] 请求 URL: ${url}`);

      const res = await fetch(url);
      const data = await res.json();
      console.log(`[switchVideoType] API 响应:`, data);
      console.log(`[switchVideoType] data.code=${data.code}, data.data 类型=${Array.isArray(data.data) ? '数组' : typeof data.data}, 长度=${data.data?.length || 0}`);

      if (data.code === 0 && Array.isArray(data.data)) {
        const username = _currentAuthor.username;
        // 更新 _authorVideosData（必须经过 mapVideo 转换，否则 downloaded 字段缺失）
        _authorVideosData[username] = { videos: {} };
        data.data.forEach(v => {
          const mapped = mapVideo(v);
          _authorVideosData[username].videos[v.video_id] = mapped;
        });
        // 重新渲染
        const videos = Object.values(_authorVideosData[username].videos);
        console.log(`[switchVideoType] 准备渲染 ${videos.length} 个视频，类型=${type}`);
        console.log(`[switchVideoType] 视频列表:`, videos.map(v => ({ id: v.video_id, title: v.title?.slice(0,20), video_type: v.video_type })));
        const currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
        renderVideoList(videos, currentFilter);

        // 更新统计
        console.log(`[switchVideoType] stats=`, data.stats);
        updateAuthorStatsByType(data.stats);
        // 更新全局进度条
        if (typeof updateAuthorGlobalProgress === 'function') {
          updateAuthorGlobalProgress();
        }
      } else {
        console.error(`[switchVideoType] API 返回异常: code=${data.code}, msg=${data.msg}`);
      }
    } catch(e) {
      console.error('[switchVideoType] 加载视频列表失败:', e);
    }
  } else {
    console.warn(`[switchVideoType] _currentAuthor 未设置，无法加载视频`);
  }
}

// 更新作者头部统计（按类型）
function updateAuthorStatsByType(data) {
  console.log(`[updateAuthorStatsByType] 接收数据:`, data);
  const shortVideoEl = document.getElementById("authorShortVideo");
  const replayEl = document.getElementById("authorReplay");
  const downloadedEl = document.getElementById("authorDownloaded");

  if (shortVideoEl) shortVideoEl.textContent = data.short_video_count || 0;
  if (replayEl) replayEl.textContent = data.replay_count || 0;
  // downloaded 显示 "已下载/总数" 格式，明确关联当前类型
  const isReplay = _currentVideoType === 'live_replay';
  const downloadedCount = isReplay
    ? (data.replay_downloaded || 0)
    : (data.short_video_downloaded || 0);
  const totalForType = isReplay
    ? (data.replay_count || 0)
    : (data.short_video_count || 0);
  if (downloadedEl) downloadedEl.textContent = downloadedCount + '/' + totalForType;

  console.log(`[updateAuthorStatsByType] 更新后: 短视频=${data.short_video_count}, 回放=${data.replay_count}, 已下载=${downloadedCount}/${totalForType}`);
}

function renderVideoList(videos, filter = 'all') {
  console.log(`[renderVideoList] 入参: videos.length=${videos.length}, filter=${filter}`);
  console.log(`[renderVideoList] _currentVideoType=${_currentVideoType}`);

  const el = document.getElementById("videoList");

  const downloadingIds = new Set();
  const progressMap = {};

  _activeTasks.forEach(task => {
    const videoId = task.video_id || '';
    // 已完成/错误的任务不算"正在下载"
    if (videoId && task.status !== 'done' && task.status !== 'completed' && task.status !== 'error') {
      downloadingIds.add(videoId);
      progressMap[videoId] = task;
    }
  });

  let filtered = videos;

  // 一级过滤：按视频类型
  if (_currentVideoType) {
    const beforeCount = filtered.length;
    filtered = filtered.filter(v => (v.video_type || 'short_video') === _currentVideoType);
    console.log(`[renderVideoList] video_type 过滤: ${beforeCount} -> ${filtered.length}, 类型=${_currentVideoType}`);
  }

  // 二级过滤：按下载状态
  // "正在下载"：在活跃任务中且未下载完成的视频
  if (filter === 'downloading') {
    const beforeCount2 = filtered.length;
    filtered = filtered.filter(v => downloadingIds.has(v.id) && !v.downloaded);
    console.log(`[renderVideoList] downloading 过滤: ${beforeCount2} -> ${filtered.length}, downloadingIds=${downloadingIds.size}`);
  } else if (filter === 'downloaded') {
    filtered = filtered.filter(v => v.downloaded);
  } else if (filter === 'pending') {
    filtered = filtered.filter(v => !v.downloaded && !downloadingIds.has(v.id));
  }

  const searchQuery = document.getElementById("videoSearchInput")?.value?.toLowerCase() || '';
  if (searchQuery) {
    filtered = filtered.filter(v => (v.title || '').toLowerCase().includes(searchQuery));
  }

  if (_dateRange.start || _dateRange.end) {
    filtered = filtered.filter(v => {
      const ts = new Date(v.create_time || v.createtime || 0).getTime();
      if (_dateRange.start && ts < _dateRange.start.getTime()) return false;
      if (_dateRange.end && ts > _dateRange.end.getTime()) return false;
      return true;
    });
  }

  if (filtered.length === 0) {
    var videoView = State.ui.getVideoViewMode();
    var viewClass = (videoView !== 'list') ? (videoView + '-view') : '';
    el.className = 'video-list no-animation ' + viewClass;
    const hasAnyVideos = videos.length > 0;
    const emptyMsg = hasAnyVideos ? '没有符合条件的视频' : '此作者还没有发布过视频';
    el.innerHTML = `<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="12" cy="12" r="3"/><line x1="2" y1="4" x2="22" y2="20"/></svg><div class="empty-title">${emptyMsg}</div></div>`;
    return;
  }

  filtered.sort((a, b) => {
    const ta = new Date(a.create_time || a.createtime || 0).getTime();
    const tb = new Date(b.create_time || b.createtime || 0).getTime();
    return tb - ta;
  });

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  if (_currentPageNum > totalPages) _currentPageNum = totalPages;
  if (_currentPageNum < 1) _currentPageNum = 1;
  const startIdx = (_currentPageNum - 1) * PAGE_SIZE;
  const pageVideos = filtered.slice(startIdx, startIdx + PAGE_SIZE);

  let html = '';
  pageVideos.forEach(video => {
    const date = video.create_time ? formatDate(video.create_time) : '未知日期';
    const title = video.title || `视频 ${video.id.slice(-8)}`;
    const selected = _selectedVideos.has(video.id) ? ' selected' : '';

    const coverUrl = video.cover_url || '';
    const fallbackAttr = coverUrl ? ` data-src-fallback="${coverUrl}"` : '';
    const coverHtml = coverUrl
      ? `<img data-src="/api/video/cover/${encodeURIComponent(_currentAuthor.username)}/${video.id}" class="lazy-img"${fallbackAttr}>`
      : `<div class="thumb-placeholder">o</div>`;

    const duration = video.duration || 0;
    const durationStr = duration > 0 ? formatDuration(duration) : '';

    const actualSize = video.actual_size || 0;
    const originalSize = video.size || 0;
    const displaySize = actualSize > 0 ? actualSize : originalSize;
    const sizeStr = displaySize > 0 ? formatFileSize(displaySize) : '';

    const width = video.width || 0;
    const height = video.height || 0;
    const resolution = width && height ? `${width}x${height}` : '';

    let statusBadge = '';
    if (video.downloaded) {
      statusBadge = `<span class="video-status-badge downloaded" data-path="${escapeAttr(video.download_path || '')}" onclick="event.stopPropagation(); openVideo(this.dataset.path)">已下载</span>`;
    } else if (downloadingIds.has(video.id)) {
      const progress = progressMap[video.id];
      const pct = progress?.percent || 0;
      const isPaused = progress?.status === 'paused';
      if (isPaused) {
        const rawDownloaded = progress?.downloaded || 0;
        const rawSize = progress?.size || 0;
        const downloaded = formatFileSize(rawDownloaded) || '--';
        const size = formatFileSize(rawSize) || '--';
        const taskId = progress?.id || '';
        statusBadge = `
          <span class="video-status-badge paused" title="服务离线，下载已暂停">
            <div class="download-header">
              <span class="progress-percent">${pct}%</span>
              <button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload('${taskId}')" title="取消下载" aria-label="取消下载">×</button>
            </div>
            <div class="progress-bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill paused-fill" style="width:${pct}%"></div></div>
            <div class="download-stats">
              <span class="stat-size">${downloaded}/${size}</span>
              <span class="stat-divider"></span><span class="stat-speed muted">已暂停</span>
            </div>
          </span>`;
      } else {
        const rawDownloaded = progress?.downloaded || 0;
        const rawSize = progress?.size || 0;
        const rawSpeed = progress?.speed || 0;
        const downloaded = formatFileSize(rawDownloaded) || '--';
        const size = formatFileSize(rawSize) || '--';
        const speed = rawSpeed > 0 ? `${formatFileSize(rawSpeed)}/s` : '--';
        const tooltip = `${downloaded}/${size} · ${speed}`;
        const taskId = progress?.id || '';
        statusBadge = `
          <span class="video-status-badge downloading" title="${tooltip}">
            <div class="download-header">
              <span class="progress-percent">${pct}%</span>
              <button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload('${taskId}')" title="取消下载" aria-label="取消下载">×</button>
            </div>
            <div class="progress-bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="download-stats">
              <span class="stat-size">${downloaded}/${size}</span>
              <span class="stat-divider"></span><span class="stat-speed${rawSpeed > 0 ? '' : ' muted'}">${speed}</span>
            </div>
          </span>`;
      }
    } else {
      statusBadge = `<span class="video-status-badge pending">待下载</span>`;
    }

    const openBtn = video.downloaded && video.download_path
      ? `<button class="video-open-btn" data-path="${escapeAttr(video.download_path)}" onclick="event.stopPropagation(); openVideo(this.dataset.path)" title="打开视频">▶</button>`
      : '';

    const rowClass = selected + (downloadingIds.has(video.id) ? ' downloading' : '');

    html += `
      <div class="video-row ${rowClass}" data-id="${video.id}">
        <div class="video-checkbox" onclick="event.stopPropagation(); toggleVideoSelect('${video.id}')" role="checkbox" aria-checked="${_selectedVideos.has(video.id) ? 'true' : 'false'}" aria-label="选择视频" tabindex="0"></div>
        <div class="video-thumb-small">
          ${coverHtml}
          ${durationStr ? `<span class="video-duration">${durationStr}</span>` : ''}
        </div>
        <div class="video-info">
          <div class="video-title">${title}</div>
          <div class="video-meta">
            <span>${date}</span>
            ${durationStr ? `<span class="meta-duration">${durationStr}</span>` : ''}
            ${resolution ? `<span class="meta-resolution">${resolution}</span>` : ''}
            ${sizeStr ? `<span class="meta-size">${sizeStr}</span>` : ''}
          </div>
        </div>
        ${statusBadge}
        ${openBtn}
      </div>
    `;
  });

  if (totalPages > 1) {
    html += buildPagination(totalPages, filtered.length);
  }

  el.innerHTML = html;
  el.classList.remove('no-animation');
  el.classList.remove('grid-view', 'compact-view');
  var videoView = State.ui.getVideoViewMode();
  if (videoView !== 'list') {
    el.classList.add(videoView + '-view');
  }
  lazyLoadImages();
  updateSelectionBar();
}

function updateVideoListIncremental(videos, filter) {
  const el = document.getElementById("videoList");
  if (!el) return;

  if (filter === undefined) {
    filter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
  }

  const downloadingIds = new Set();
  const progressMap = {};
  _activeTasks.forEach(task => {
    const videoId = task.video_id || '';
    if (videoId && task.status !== 'done' && task.status !== 'completed' && task.status !== 'error') {
      downloadingIds.add(videoId);
      progressMap[videoId] = task;
    }
  });

  let filtered = getFilteredVideos(videos, filter, downloadingIds);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  if (_currentPageNum > totalPages) _currentPageNum = totalPages;
  if (_currentPageNum < 1) _currentPageNum = 1;
  const startIdx = (_currentPageNum - 1) * PAGE_SIZE;
  const pageVideos = filtered.slice(startIdx, startIdx + PAGE_SIZE);

  const rows = el.querySelectorAll('.video-row');
  const currentIds = [...rows].map(r => r.dataset.id);
  const newIds = pageVideos.map(v => v.id);

  const hasStructuralChange = currentIds.length !== newIds.length ||
    currentIds.some((id, i) => id !== newIds[i]);

  if (hasStructuralChange) {
    renderVideoList(videos, filter);
    return;
  }

  updateVideoStatusIncremental(el, videos, downloadingIds, progressMap);
}

function getFilteredVideos(videos, filter, downloadingIds) {
  let filtered = videos;

  // 一级过滤：按视频类型
  if (_currentVideoType) {
    filtered = filtered.filter(v => (v.video_type || 'short_video') === _currentVideoType);
  }

  // 二级过滤：按下载状态
  // "正在下载"：在活跃任务中且未下载完成的视频
  if (filter === 'downloading') {
    filtered = filtered.filter(v => downloadingIds.has(v.id) && !v.downloaded);
  } else if (filter === 'downloaded') {
    filtered = filtered.filter(v => v.downloaded);
  } else if (filter === 'pending') {
    filtered = filtered.filter(v => !v.downloaded && !downloadingIds.has(v.id));
  }

  const searchQuery = document.getElementById("videoSearchInput")?.value?.toLowerCase() || '';
  if (searchQuery) {
    filtered = filtered.filter(v => (v.title || '').toLowerCase().includes(searchQuery));
  }

  if (_dateRange.start || _dateRange.end) {
    filtered = filtered.filter(v => {
      const ts = new Date(v.create_time || v.createtime || 0).getTime();
      if (_dateRange.start && ts < _dateRange.start.getTime()) return false;
      if (_dateRange.end && ts > _dateRange.end.getTime()) return false;
      return true;
    });
  }

  filtered.sort((a, b) => {
    const ta = new Date(a.create_time || a.createtime || 0).getTime();
    const tb = new Date(b.create_time || b.createtime || 0).getTime();
    return tb - ta;
  });
  return filtered;
}

function updateVideoStatusIncremental(el, videos, downloadingIds, progressMap) {
  videos.forEach(video => {
    const row = el.querySelector(`.video-row[data-id="${video.id}"]`);
    if (!row) return;

    const badge = row.querySelector('.video-status-badge');
    if (!badge) return;

    if (video.downloaded) {
      if (!badge.classList.contains('downloaded')) {
        badge.className = 'video-status-badge downloaded';
        badge.textContent = '已下载';
        if (video.download_path) {
          badge.dataset.path = video.download_path;
          badge.onclick = (e) => { e.stopPropagation(); openVideo(badge.dataset.path); };
        }
      }
    } else if (downloadingIds.has(video.id)) {
      const task = progressMap[video.id];
      if (task) {
        if (task.status === 'paused') {
          if (!badge.classList.contains('paused')) {
            badge.className = 'video-status-badge paused';
            const pct = task.percent || 0;
            const dlStr = formatFileSize(task.downloaded || 0) || '--';
            const szStr = formatFileSize(task.size || 0) || '--';
            badge.innerHTML = `
              <div class="download-header">
                <span class="progress-percent">${pct}%</span>
                <button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload('${task.id || ''}')" title="取消下载" aria-label="取消下载">×</button>
              </div>
              <div class="progress-bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill paused-fill" style="width:${pct}%"></div></div>
              <div class="download-stats">
                <span class="stat-size">${dlStr}/${szStr}</span>
                <span class="stat-divider"></span><span class="stat-speed muted">已暂停</span>
              </div>`;
            badge.title = '服务离线，下载已暂停';
          }
        } else if (badge.classList.contains('paused') && !badge.classList.contains('resuming')) {
          // paused → resuming transition
          badge.className = 'video-status-badge resuming';
          const pct = task.percent || 0;
          badge.textContent = '恢复中 (' + pct + '%)';
          badge.title = '正在恢复下载...';
          // actual downloading badge will replace on next progress SSE
        } else if (!badge.classList.contains('downloading') && !badge.classList.contains('resuming')) {
          badge.className = 'video-status-badge downloading';
          const pct = task.percent || 0;
          const dlStr = formatFileSize(task.downloaded || 0) || '--';
          const szStr = formatFileSize(task.size || 0) || '--';
          const rawSpeed = task.speed || 0;
          const speedStr = rawSpeed > 0 ? `${formatFileSize(rawSpeed)}/s` : '--';
          badge.innerHTML = `
            <div class="download-header">
              <span class="progress-percent">${pct}%</span>
              <button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload('${task.id}')">×</button>
            </div>
            <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
            <div class="download-stats">
              <span class="stat-size">${dlStr}/${szStr}</span>
              <span class="stat-divider"></span><span class="stat-speed${rawSpeed > 0 ? '' : ' muted'}">${speedStr}</span>
            </div>`;
          badge.title = `${dlStr}/${szStr}`;
        } else {
          const pct = task.percent || 0;
          const pctEl = badge.querySelector('.progress-percent');
          if (pctEl) pctEl.textContent = `${pct}%`;
          const fill = badge.querySelector('.progress-fill');
          if (fill) fill.style.width = `${pct}%`;
          const sizeEl = badge.querySelector('.stat-size');
          if (sizeEl) sizeEl.textContent = `${formatFileSize(task.downloaded || 0) || '--'}/${formatFileSize(task.size || 0) || '--'}`;
          const speedEl = badge.querySelector('.stat-speed');
          if (speedEl) {
            const rawSpeed = task.speed || 0;
            speedEl.textContent = rawSpeed > 0 ? `${formatFileSize(rawSpeed)}/s` : '--';
            speedEl.classList.toggle('muted', rawSpeed === 0);
          }
          badge.title = `${formatFileSize(task.downloaded || 0) || '--'}/${formatFileSize(task.size || 0) || '--'}`;
        }
      }
    } else {
      if (!badge.classList.contains('pending')) {
        badge.className = 'video-status-badge pending';
        badge.textContent = '待下载';
      }
    }

    row.classList.toggle('downloading', downloadingIds.has(video.id));
  });
}

function _removeRowAndUpdatePagination(row) {
  var listEl = document.getElementById("videoList");
  if (!listEl || !row) return;

  row.remove();

  // 重新渲染当前页以补全数据（避免页面缺行）
  var videos = Object.values(_authorVideosData[_currentAuthor?.username]?.videos || {});
  if (videos.length > 0) {
    var currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
    renderVideoList(videos, currentFilter);
  } else {
    listEl.innerHTML = '<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="12" cy="12" r="3"/><line x1="2" y1="4" x2="22" y2="20"/></svg><div class="empty-title">没有符合条件的视频</div></div>';
  }
}

function updateSingleVideoProgress(videoId, task) {
  var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
  if (!row) {
    // SSE 广播所有任务的进度，当前页面可能不包含该视频（其他作者或未显示的分页）
    return;
  }

  var badge = row.querySelector('.video-status-badge');
  if (!badge) {
    console.warn('[SSE][渲染层] 未找到 badge: videoId=%s', videoId);
    return;
  }

  var pct = task.percent || 0;
  var dlStr = formatFileSize(task.downloaded || 0) || '--';
  var szStr = formatFileSize(task.size || 0) || '--';
  var hasSpeed = task.speed > 0;
  var speed = hasSpeed ? formatFileSize(task.speed) + '/s' : '--/s';

  if (badge.classList.contains('downloading')) {
    console.log('[SSE][渲染层] 快速路径: id=%s, %s%%, %s/%s, %s', videoId, pct, dlStr, szStr, hasSpeed ? speed : '--');
    var pctEl = badge.querySelector('.progress-percent');
    if (pctEl) pctEl.textContent = pct + '%';
    var fill = badge.querySelector('.progress-fill');
    if (fill) fill.style.width = pct + '%';
    var bar = badge.querySelector('.progress-bar');
    if (bar) bar.setAttribute('aria-valuenow', pct);
    var sizeEl = badge.querySelector('.stat-size');
    if (sizeEl) sizeEl.textContent = dlStr + '/' + szStr;
    var speedEl = badge.querySelector('.stat-speed');
    if (speedEl) {
      speedEl.textContent = speed;
      speedEl.classList.toggle('muted', !hasSpeed);
    }
  } else {
    console.log('[SSE][渲染层] 慢速路径(切换状态): id=%s, %s%%, %s/%s', videoId, pct, dlStr, szStr);

    var currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
    if (currentFilter === 'pending') {
      _removeRowAndUpdatePagination(row);
      return;
    }

    badge.className = 'video-status-badge downloading';
    var taskId = task.id || '';
    badge.innerHTML =
      '<div class="download-header">' +
        '<span class="progress-percent">' + pct + '%</span>' +
        '<button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload(\'' + taskId + '\')" aria-label="取消下载">×</button>' +
      '</div>' +
      '<div class="progress-bar" role="progressbar" aria-valuenow="' + pct + '" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" style="width:' + pct + '%"></div></div>' +
      '<div class="download-stats">' +
        '<span class="stat-size">' + dlStr + '/' + szStr + '</span>' +
        '<span class="stat-divider"></span><span class="stat-speed' + (hasSpeed ? '' : ' muted') + '">' + speed + '</span>' +
      '</div>';
    row.classList.add('downloading');
  }
}

function updateSingleVideoCompleted(videoId, video) {
  var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
  if (!row) {
    // 视频不在当前页面（其他作者或未显示的分页）
    return;
  }

  var badge = row.querySelector('.video-status-badge');
  if (!badge) return;

  console.log('[SSE][渲染层][完成] 切换为已下载: id=%s, path=%s', videoId, video.download_path || '');

  var currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
  // 完成的视频不属于"正在下载"和"待下载"筛选视图，需移除并重新渲染
  if (currentFilter === 'downloading' || currentFilter === 'pending') {
    _removeRowAndUpdatePagination(row);
    return;
  }

  badge.className = 'video-status-badge downloaded completed-anim';
  badge.dataset.path = video.download_path || '';
  badge.onclick = video.download_path ? function(e) { e.stopPropagation(); openVideo(video.download_path); } : null;
  badge.textContent = '已下载';
  setTimeout(function() { badge.classList.remove('completed-anim'); }, 400);

  row.classList.remove('downloading');

  if (!row.querySelector('.video-open-btn') && video.download_path) {
    var openBtn = document.createElement('button');
    openBtn.className = 'video-open-btn';
    openBtn.dataset.path = video.download_path;
    openBtn.title = '打开视频';
    openBtn.textContent = '▶';
    openBtn.onclick = function(e) { e.stopPropagation(); openVideo(this.dataset.path); };
    row.appendChild(openBtn);
  }
}

function updateSingleVideoError(videoId) {
  var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
  if (!row) {
    // 视频不在当前页面（其他作者或未显示的分页）
    return;
  }

  var badge = row.querySelector('.video-status-badge');
  if (!badge) return;

  console.log('[SSE][渲染层][错误] 切换为错误状态: id=%s', videoId);

  var currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
  // 失败的视频不属于"正在下载"和"已下载"筛选视图，需移除并重新渲染
  if (currentFilter === 'downloading' || currentFilter === 'downloaded') {
    _removeRowAndUpdatePagination(row);
    return;
  }

  badge.className = 'video-status-badge error';
  badge.textContent = '下载失败';
  badge.onclick = null;
  badge.setAttribute('role', 'alert');

  row.classList.remove('downloading');

  // 移除播放按钮（如果有）
  var openBtn = row.querySelector('.video-open-btn');
  if (openBtn) openBtn.remove();
}