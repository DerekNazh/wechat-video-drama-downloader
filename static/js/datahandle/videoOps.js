// 视频操作数据处理

var _batchCreateAbort = false;

async function _batchCreateWithProgress(videoIds, title) {
  // 前置检测：Go 服务和微信连接
  var goOnline = (typeof State !== 'undefined' && State.service) ? State.service.isGoOnline() : _goOnline;
  if (!goOnline) {
    showToast({ type: 'error', title: '无法下载', message: 'Go 服务未启动，请先启动 Go 服务' });
    return { success: 0, failed: 0, total: videoIds.length, cancelled: false, successIds: [], failedIds: [] };
  }
  var wechatConnected = (typeof State !== 'undefined' && State.service) ? State.service.isWechatConnected() : false;
  if (!wechatConnected) {
    showToast({ type: 'error', title: '无法下载', message: '微信未连接，请先登录微信' });
    return { success: 0, failed: 0, total: videoIds.length, cancelled: false, successIds: [], failedIds: [] };
  }

  var total = videoIds.length;

  // 2 个以下：静默下载，不弹进度框
  if (total <= 2) {
    return await _batchCreateSilent(videoIds);
  }

  return await _batchCreateWithDialog(videoIds, title, total);
}

async function _batchCreateSilent(videoIds) {
  var success = 0;
  var failed = 0;
  var total = videoIds.length;
  var successIds = [];
  var failedIds = [];

  for (var i = 0; i < videoIds.length; i++) {
    try {
      var res = await fetch('/api/task/batch-create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_ids: [videoIds[i]] })
      });
      var data = await res.json();
      if (data.code === 0 && data.data && data.data.count > 0) {
        success++;
        successIds.push(videoIds[i]);
      } else {
        failed++;
        failedIds.push(videoIds[i]);
      }
    } catch(e) {
      failed++;
      failedIds.push(videoIds[i]);
    }
  }

  if (success > 0) {
    if (failed > 0) {
      showToast({ type: 'warning', title: '部分添加成功', message: `${success}/${total} 个已添加，${failed} 个失败` });
    } else {
      showToast({ type: 'success', title: '添加成功', message: `已将 ${success} 个视频添加到下载队列` });
    }
  } else {
    showToast({ type: 'error', title: '添加失败', message: '视频添加失败，请检查服务状态' });
  }

  if (typeof refreshActiveTasks === 'function') {
    await refreshActiveTasks();
  }

  return { success: success, failed: failed, total: total, cancelled: false, successIds: successIds, failedIds: failedIds };
}

async function _batchCreateWithDialog(videoIds, title, total) {
  var CONCURRENCY = 3;
  var success = 0;
  var failed = 0;
  var completed = 0;
  var consecutiveFailures = 0;
  var successIds = [];
  var failedIds = [];
  _batchCreateAbort = false;

  // 如果对话框已打开（多类型选择路径），原地切换；否则新建
  if (BatchProgressDialog.isOpen()) {
    BatchProgressDialog.switchToProgress({ total: total, title: title, onCancel: function() { _batchCreateAbort = true; } });
  } else {
    BatchProgressDialog.open({ total: total, title: title, onCancel: function() { _batchCreateAbort = true; } });
  }

  // 并发池：同时最多 CONCURRENCY 个请求
  var queue = videoIds.slice();
  var workers = [];

  for (var w = 0; w < CONCURRENCY; w++) {
    workers.push((async function() {
      while (queue.length > 0 && !_batchCreateAbort) {
        var videoId = queue.shift();
        if (!videoId) break;

        try {
          var res = await fetch('/api/task/batch-create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_ids: [videoId] })
          });
          var data = await res.json();
          if (data.code === 0 && data.data && data.data.count > 0) {
            success++;
            successIds.push(videoId);
            consecutiveFailures = 0;
          } else {
            failed++;
            failedIds.push(videoId);
            consecutiveFailures++;
          }
        } catch(e) {
          failed++;
          failedIds.push(videoId);
          consecutiveFailures++;
        }

        completed++;

        // 连续 3 次失败 → 检查 Go 是否离线，离线则停止
        if (consecutiveFailures >= 3) {
          try {
            var checkRes = await fetch('/api/status');
            var checkData = await checkRes.json();
            var goOnline = checkData.data && checkData.data.service_online;
            var wechatOk = checkData.data && checkData.data.wechat_connected;
            if (!goOnline || !wechatOk) {
              _batchCreateAbort = true;
              var reason = !goOnline ? 'Go 服务已离线' : '微信已断开';
              BatchProgressDialog.update(completed, total, reason + '，停止添加');
              break;
            }
          } catch(e) {
            _batchCreateAbort = true;
            BatchProgressDialog.update(completed, total, '服务检测失败，停止添加');
            break;
          }
          consecutiveFailures = 0;
        }

        var detail = failed > 0 ? (success + ' 个成功, ' + failed + ' 个失败') : '';
        BatchProgressDialog.update(completed, total, detail);
      }
    })());
  }

  await Promise.all(workers);

  var result = { success: success, failed: failed, total: total, cancelled: _batchCreateAbort, successIds: successIds, failedIds: failedIds };
  BatchProgressDialog.close(result);

  if (success > 0) {
    if (failed > 0) {
      showToast({ type: 'warning', title: '部分添加成功', message: `已将 ${success}/${total} 个视频添加到下载队列，${failed} 个失败` });
    } else if (_batchCreateAbort) {
      showToast({ type: 'warning', title: '已停止', message: `已添加 ${success} 个视频，剩余任务已停止` });
    } else {
      showToast({ type: 'success', title: '添加成功', message: `已将 ${success} 个视频添加到下载队列` });
    }
  } else if (_batchCreateAbort) {
    showToast({ type: 'warning', title: '已停止', message: '批量添加已停止' });
  } else {
    showToast({ type: 'error', title: '添加失败', message: '全部视频添加失败，请检查服务状态' });
  }

  // 最终刷新活跃任务
  if (typeof refreshActiveTasks === 'function') {
    await refreshActiveTasks();
  }

  return result;
}

function _setSelectionActionsDisabled(disabled) {
  const actions = document.querySelectorAll('.selection-actions button');
  actions.forEach(btn => {
    btn.disabled = disabled;
    if (disabled) {
      btn.style.opacity = '0.5';
      btn.style.cursor = 'not-allowed';
    } else {
      btn.style.opacity = '';
      btn.style.cursor = '';
    }
  });
}

async function downloadSelected() {
  if (_selectedVideos.size === 0) return;
  if (!_currentAuthor) return;

  var downloadBtn = document.querySelector('.btn-primary[onclick="downloadSelected()"]');
  if (downloadBtn && downloadBtn.disabled) return;

  var _username = _currentAuthor?.username;
  if (!_username) return;
  const videos = _authorVideosData[_username]?.videos || {};
  const selectedIds = Array.from(_selectedVideos);

  // 检测非待下载状态的视频（已下载 + 正在下载）
  const nonPendingIds = selectedIds.filter(id => {
    const video = videos[id];
    if (!video) return false;
    const isDownloading = _activeTasks.some(t => t.video_id === id && t.status !== 'done' && t.status !== 'completed' && t.status !== 'error' && t.status !== 'failed');
    return video.downloaded || isDownloading;
  });

  if (nonPendingIds.length > 0) {
    const downloadedCount = nonPendingIds.filter(id => videos[id]?.downloaded).length;
    const downloadingCount = nonPendingIds.length - downloadedCount;
    let detail = '';
    if (downloadedCount > 0 && downloadingCount > 0) {
      detail = `${downloadedCount} 个已下载，${downloadingCount} 个正在下载`;
    } else if (downloadedCount > 0) {
      detail = `${downloadedCount} 个已下载`;
    } else {
      detail = `${downloadingCount} 个正在下载`;
    }
    showToast({ type: 'warning', title: '选择中有非待下载状态视频', message: `${detail}，请只选择待下载的视频` });
    return;
  }

  const pendingIds = selectedIds.filter(id => {
    const video = videos[id];
    return video && !video.downloaded;
  });

  if (pendingIds.length === 0) {
    showToast({ type: 'warning', title: '无需下载', message: '所选视频均已下载' });
    clearSelection();
    return;
  }

  _setSelectionActionsDisabled(true);

  if (downloadBtn) {
    downloadBtn.disabled = true;
    downloadBtn.textContent = '添加中...';
  }

  var result = await _batchCreateWithProgress(pendingIds, '添加下载');

  if (result.success > 0) {
    const currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
    var idsToRemove = result.successIds || pendingIds;
    if (currentFilter === 'pending') {
      idsToRemove.forEach(videoId => {
        var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
        if (row) _removeRowAndUpdatePagination(row);
      });
    } else {
      updateDownloadStatus(idsToRemove);
    }

    clearSelection();
  }

  if (result.failedIds && result.failedIds.length > 0) {
    showToast({ type: 'warning', title: '部分添加失败', message: result.failedIds.length + ' 个视频添加失败（URL 可能已过期）' });
  }

  if (downloadBtn) {
    downloadBtn.disabled = false;
    downloadBtn.textContent = '下载';
  }
  _setSelectionActionsDisabled(false);
}

function updateDownloadStatus(videoIds) {
  videoIds.forEach(videoId => {
    const row = document.querySelector(`.video-row[data-id="${videoId}"]`);
    if (!row) return;

    const task = _activeTasks.find(t => t.video_id === videoId);
    const badge = row.querySelector('.video-status-badge');
    if (!badge) return;

    if (task) {
      const pct = task.percent || 0;
      const dlStr = formatFileSize(task.downloaded || 0) || '--';
      const szStr = formatFileSize(task.size || 0) || '--';
      const speedStr = task.speed ? `${formatFileSize(task.speed)}/s` : '--';
      const tooltip = `${dlStr}/${szStr} · ${speedStr}`;
      badge.className = 'video-status-badge downloading';
      badge.title = tooltip;
      var hasSpeed = task.speed > 0;
      badge.innerHTML = `
        <div class="download-header">
          <span class="progress-percent">${pct}%</span>
          <button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload('${task.id}')" aria-label="取消下载">×</button>
        </div>
        <div class="progress-bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" style="width:${pct}%"></div></div>
        <div class="download-stats">
          <span class="stat-size">${dlStr}/${szStr}</span>
          <span class="stat-divider"></span><span class="stat-speed${hasSpeed ? '' : ' muted'}">${speedStr}</span>
        </div>`;
      row.classList.add('downloading');
    }
  });
}

async function deleteSelected() {
  if (_selectedVideos.size === 0) return;
  if (!_currentAuthor) return;

  var _username = _currentAuthor.username;
  if (!_username) return;
  const videos = _authorVideosData[_username]?.videos || {};
  const allIds = Array.from(_selectedVideos);
  const downloadedIds = allIds.filter(id => videos[id]?.downloaded);
  const recordOnlyIds = allIds.filter(id => !videos[id]?.downloaded);

  showDeleteConfirmDialog(
    allIds.length,
    downloadedIds.length,
    recordOnlyIds.length,
    clearSelection,
    async () => {
      _setSelectionActionsDisabled(true);
      const toDelete = allIds;
      if (toDelete.length === 0) {
        showToast({ type: 'warning', title: '无需删除', message: '所选视频均不存在' });
        clearSelection();
        _setSelectionActionsDisabled(false);
        return;
      }
      await doDeleteSelected(toDelete);
      clearSelection();
      _setSelectionActionsDisabled(false);
    }
  );
}

async function doDeleteSelected(selectedArr) {
  try {
    const res = await fetch('/api/video/batch-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_ids: selectedArr,
      })
    });
    const data = await res.json();

    if (data.code === 0) {
      const deleted = data.data?.deleted || selectedArr.length;
      showToast({ type: 'success', title: '删除成功', message: `已删除 ${deleted} 个视频` });

      // 从本地数据中移除
      if (_currentAuthor) {
        const authorData = _authorVideosData[_currentAuthor?.username || ''];
        if (authorData && authorData.videos) {
          selectedArr.forEach(id => {
            delete authorData.videos[id];
          });
          const videos = Object.values(authorData.videos);

          // 逐个移除 DOM 行，避免全量渲染
          var listEl = document.getElementById("videoList");
          if (listEl) {
            selectedArr.forEach(id => {
              var row = listEl.querySelector('.video-row[data-id="' + id + '"]');
              if (row) row.remove();
            });

            var remainingRows = listEl.querySelectorAll('.video-row');
            var currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';

            if (remainingRows.length === 0) {
              // 当前页删空了
              var downloadingIds = (typeof _getDownloadingIds === 'function') ? _getDownloadingIds() : new Set();
              var filtered = (typeof getFilteredVideos === 'function') ? getFilteredVideos(videos, currentFilter, downloadingIds) : videos;

              if (filtered.length === 0) {
                var videoView = (typeof State !== 'undefined' && State.ui) ? State.ui.getVideoViewMode() : 'list';
                var viewClass = (videoView !== 'list') ? (videoView + '-view') : '';
                listEl.className = 'video-list no-animation ' + viewClass;
                listEl.innerHTML = '<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="12" cy="12" r="3"/><line x1="2" y1="4" x2="22" y2="20"/></svg><div class="empty-title">没有符合条件的视频</div></div>';
              } else {
                if (typeof _currentPageNum !== 'undefined' && _currentPageNum > 1) _currentPageNum--;
                renderVideoList(videos, currentFilter);
              }
            } else if (remainingRows.length < Math.floor(PAGE_SIZE / 2)) {
              // 当前页少于一半，触发补行渲染
              renderVideoList(videos, currentFilter);
            } else {
              // 只更新分页数字
              if (typeof _updatePaginationCount === 'function') {
                _updatePaginationCount();
              }
            }
          }

          updateAuthorStats(videos);
        }
      }
    } else {
      showToast({ type: 'error', title: '删除失败', message: data.message || '未知错误' });
    }
  } catch(e) {
    showToast({ type: 'error', title: '删除失败', message: e.message });
  }
}

async function downloadAllPending() {
  if (!_currentAuthor) return;

  var _username = _currentAuthor.username;
  if (!_username) return;
  var videos = _authorVideosData[_username];
  if (!videos) return;

  // 排除已下载 + 正在下载中的视频，只保留真正的"待下载"
  var downloadingIds = new Set(_activeTasks.filter(function(t) { return t.status !== 'done' && t.status !== 'completed' && t.status !== 'error' && t.status !== 'failed'; }).map(function(t) { return t.video_id; }));
  var pendingVideos = Object.entries(videos.videos || {}).filter(function(entry) {
    return !entry[1].downloaded && !downloadingIds.has(entry[0]);
  });

  if (pendingVideos.length === 0) {
    showToast({ type: 'warning', title: '没有待下载视频', message: '当前作者所有视频已下载' });
    return;
  }

  var shortVideoPending = pendingVideos.filter(function(entry) { return (entry[1].video_type || 'short_video') === 'short_video'; });
  var replayPending = pendingVideos.filter(function(entry) { return entry[1].video_type === 'live_replay'; });
  var totalPending = pendingVideos.length;
  var nickname = _currentAuthor?.nickname || '';

  // 展示选择对话框（单一类型时只有对应选项，多种类型时全部展示）
  _showDownloadTypeSelect(shortVideoPending.length, replayPending.length, totalPending, nickname, pendingVideos);
}

function _showDownloadTypeSelect(shortCount, replayCount, totalCount, nickname, pendingVideos) {
  // 构建类型按钮
  var typeBtnsHtml = '';
  typeBtnsHtml += '<button class="batch-type-btn" data-type="all"><span class="batch-type-label">全部下载</span><span class="batch-type-count">' + totalCount + ' 个</span></button>';
  if (shortCount > 0) {
    typeBtnsHtml += '<button class="batch-type-btn" data-type="short_video"><span class="batch-type-label">短视频</span><span class="batch-type-count">' + shortCount + ' 个</span></button>';
  }
  if (replayCount > 0) {
    typeBtnsHtml += '<button class="batch-type-btn" data-type="live_replay"><span class="batch-type-label">直播回放</span><span class="batch-type-count">' + replayCount + ' 个</span></button>';
  }

  BatchProgressDialog.open({ total: 0, title: '选择下载范围' });

  var dialogBox = document.querySelector('#batchProgressDialog .dialog-box');
  if (!dialogBox) return;

  dialogBox.innerHTML =
    '<div class="dialog-icon-wrapper">' +
      '<div class="dialog-icon info">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
          '<path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>' +
        '</svg>' +
      '</div>' +
    '</div>' +
    '<div class="dialog-title">下载全部待下载视频</div>' +
    '<div class="dialog-content">' +
      '<p class="batch-type-hint">' + nickname + ' 共有 ' + totalCount + ' 个待下载视频</p>' +
      '<div class="batch-type-options">' + typeBtnsHtml + '</div>' +
    '</div>' +
    '<div class="dialog-buttons">' +
      '<button class="btn-dialog" id="batchTypeCancelBtn">取消</button>' +
      '<button class="btn-dialog primary" id="batchTypeStartBtn">开始下载</button>' +
    '</div>';

  // 取消按钮
  var cancelBtn = dialogBox.querySelector('#batchTypeCancelBtn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function() {
      BatchProgressDialog.close(null);
    });
  }

  // 默认选中"全部下载"
  var allBtn = dialogBox.querySelector('.batch-type-btn[data-type="all"]');
  if (allBtn) allBtn.classList.add('selected');

  // 类型选择按钮：点击切换选中
  var typeBtns = dialogBox.querySelectorAll('.batch-type-btn');
  typeBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      typeBtns.forEach(function(b) { b.classList.remove('selected'); });
      btn.classList.add('selected');
      var startBtn = dialogBox.querySelector('#batchTypeStartBtn');
      if (startBtn) startBtn.disabled = false;
    });
  });

  // 开始下载按钮
  var startBtn = dialogBox.querySelector('#batchTypeStartBtn');
  if (startBtn) {
    startBtn.addEventListener('click', function() {
      var selectedBtn = dialogBox.querySelector('.batch-type-btn.selected');
      if (!selectedBtn) return;

      var selectedType = selectedBtn.getAttribute('data-type');
      var filteredIds;
      if (selectedType === 'short_video') {
        filteredIds = pendingVideos.filter(function(entry) { return (entry[1].video_type || 'short_video') === 'short_video'; }).map(function(entry) { return entry[0]; });
      } else if (selectedType === 'live_replay') {
        filteredIds = pendingVideos.filter(function(entry) { return entry[1].video_type === 'live_replay'; }).map(function(entry) { return entry[0]; });
      } else {
        filteredIds = pendingVideos.map(function(entry) { return entry[0]; });
      }

      if (filteredIds.length === 0) {
        showToast({ type: 'warning', title: '没有待下载视频', message: '所选类型没有待下载视频' });
        return;
      }

      _startBatchProgress(filteredIds);
    });
  }
}

function _startBatchProgress(videoIds) {
  // 前置检测（多类型路径）
  var goOnline = (typeof State !== 'undefined' && State.service) ? State.service.isGoOnline() : _goOnline;
  if (!goOnline) {
    BatchProgressDialog.close(null);
    showToast({ type: 'error', title: '无法下载', message: 'Go 服务未启动，请先启动 Go 服务' });
    return;
  }
  var wechatConnected = (typeof State !== 'undefined' && State.service) ? State.service.isWechatConnected() : false;
  if (!wechatConnected) {
    BatchProgressDialog.close(null);
    showToast({ type: 'error', title: '无法下载', message: '微信未连接，请先登录微信' });
    return;
  }

  _batchCreateWithProgress(videoIds, '全部下载').then(function(result) {
    if (result.success > 0) {
      var currentFilter = document.querySelector('.video-tab.active');
      var tab = currentFilter ? currentFilter.dataset.tab : 'all';
      if (tab === 'pending') {
        (result.successIds || videoIds).forEach(function(videoId) {
          var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
          if (row) _removeRowAndUpdatePagination(row);
        });
      } else {
        updateDownloadStatus(result.successIds || videoIds);
      }
    }
    if (result.failedIds && result.failedIds.length > 0) {
      showToast({ type: 'warning', title: '部分添加失败', message: result.failedIds.length + ' 个视频添加失败（URL 可能已过期）' });
    }
    var btn = document.querySelector('.btn-primary[onclick="downloadAllPending()"]');
    if (btn) { btn.disabled = false; btn.textContent = '全部下载'; }
  });

  var btn = document.querySelector('.btn-primary[onclick="downloadAllPending()"]');
  if (btn) { btn.disabled = true; btn.textContent = '添加中...'; }
}

async function refreshAuthorVideos() {
  if (!_currentAuthor) return;

  await refreshAfterVideoChange();

  const authorData = _authorVideosData[_currentAuthor.username];
  if (authorData) {
    const videos = Object.values(authorData.videos || {});
    updateVideoListIncremental(videos);
  }
}

async function resyncAuthorVideos(e) {
  if (e) e.preventDefault();

  const btn = e?.target;
  if (btn) {
    btn.disabled = true;
    btn.textContent = '同步中...';
  }

  showToast({ type: 'info', title: '正在同步', message: '获取作者最新视频列表...' });

  const authorId = _currentAuthor.id;

  try {
    const data = await fetchWithErrorHandling(`/api/video/author/${authorId}/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }, '同步作者视频');

    if (data && data.code === 0) {
      const added = data.data?.added || 0;
      showToast({ type: 'success', title: '同步完成', message: `新增 ${added} 个视频` });
      await doResyncAuthorVideos();
    }
  } catch(err) {
    showToast({ type: 'error', title: '同步失败', message: err.message || '网络错误' });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '重新同步';
    }
  }
}

async function doResyncAuthorVideos() {
  if (!_currentAuthor) return;
  await refreshAfterVideoChange();

  const authorData = _authorVideosData[_currentAuthor?.username || ''];
  if (authorData) {
    const videos = Object.values(authorData.videos || {});
    updateVideoListIncremental(videos);
    updateAuthorStats(videos);
  }
}

// 取消下载任务
function cancelDownload(taskId) {
  if (!taskId) {
    showToast({ type: 'warning', title: '取消失败', message: '任务ID不存在' });
    return;
  }

  // 解析当前 taskId：Go 重启后 resume 创建新 task_id，DOM 中的可能是旧 id
  var task = State.tasks.getByTaskId(taskId);
  var videoId = task ? task.video_id : null;
  if (!task) {
    // DOM 中的 taskId 已过期，通过 videoId 查找当前任务
    var row = document.querySelector('.video-row[data-id]');
    var rows = document.querySelectorAll('.video-row');
    rows.forEach(function(r) {
      var btn = r.querySelector('.cancel-btn');
      if (btn && btn.getAttribute('onclick') && btn.getAttribute('onclick').indexOf(taskId) >= 0) {
        videoId = r.getAttribute('data-id');
      }
    });
    if (videoId) task = State.tasks.get(videoId);
  }
  if (task) taskId = task.id;
  if (!videoId) videoId = task ? task.video_id : null;

  // 立即标记为已取消（在 HTTP 请求发出前就标记，防止竞态）
  // 不设 TTL 过期，收到终态 SSE 消息时自动清除
  if (typeof _cancelledTaskIds !== 'undefined' && taskId) {
    _cancelledTaskIds[taskId] = true;
  }

  apiFetch('/api/task/cancel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId })
  })
    .then(r => r.json())
    .then(data => {
      if (data.code === 0) {
        showToast({ type: 'success', title: '已取消', message: '下载任务已取消' });
        updateCancelStatus(taskId, videoId);
      } else {
        // 取消失败，清除标记
        if (typeof _cancelledTaskIds !== 'undefined') {
          delete _cancelledTaskIds[taskId];
        }
        showToast({ type: 'error', title: '取消失败', message: data.message || '未知错误' });
      }
    })
    .catch(e => {
      // 网络错误，清除标记
      if (typeof _cancelledTaskIds !== 'undefined') {
        delete _cancelledTaskIds[taskId];
      }
      showToast({ type: 'error', title: '取消失败', message: e.message });
    });
}

async function retryDownload(videoId) {
  if (!videoId) return;

  var authorData = _authorVideosData[_currentAuthor?.username];
  if (!authorData) return;

  var video = authorData.videos[videoId];
  if (!video) return;

  var badge = document.querySelector('.video-row[data-id="' + videoId + '"] .video-status-badge');
  if (badge) {
    badge.className = 'video-status-badge pending';
    badge.innerHTML = '<span class="waiting-text">等待中</span>';
    badge.title = '正在重新创建下载任务...';
  }

  try {
    var res = await fetch('/api/task/batch-create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_ids: [videoId] })
    });
    var data = await res.json();

    if (data.code === 0 && data.data && data.data.count > 0) {
      showToast({ type: 'success', title: '重新下载', message: '已重新创建下载任务' });
      if (typeof refreshActiveTasks === 'function') refreshActiveTasks();
    } else {
      if (badge) {
        badge.className = 'video-status-badge failed';
        badge.innerHTML = '<span class="failed-text">恢复失败</span><button class="retry-btn" onclick="event.stopPropagation(); retryDownload(\'' + videoId + '\')" title="重新下载" aria-label="重新下载">↻</button>';
        badge.title = data.msg || '重新下载失败';
      }
      showToast({ type: 'error', title: '重新下载失败', message: data.msg || '未知错误' });
    }
  } catch (e) {
    if (badge) {
      badge.className = 'video-status-badge failed';
      badge.innerHTML = '<span class="failed-text">恢复失败</span><button class="retry-btn" onclick="event.stopPropagation(); retryDownload(\'' + videoId + '\')" title="重新下载" aria-label="重新下载">↻</button>';
      badge.title = '网络错误';
    }
    showToast({ type: 'error', title: '重新下载失败', message: e.message });
  }
}

function updateCancelStatus(taskId, videoId) {
  State.tasks.removeByTaskId(taskId);
  _activeTasks = State.tasks.all();

  // 通知 ReactiveRenderer 任务已取消，刷新"正在下载"标签
  if (typeof State !== 'undefined' && State.emit) {
    State.emit('tasks:cancel', { taskId: taskId, videoId: videoId });
  }

  if (videoId) {
    var currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    if (row) {
      if (currentFilter === 'downloading') {
        _removeRowAndUpdatePagination(row);
      } else {
        var badge = row.querySelector('.video-status-badge');
        if (badge) {
          badge.className = 'video-status-badge pending';
          badge.textContent = '待下载';
        }
        row.classList.remove('downloading');
      }
    }
  }
}

// 打开视频文件
function openVideo(filePath) {
  if (!filePath) {
    showToast({ type: 'warning', title: '打开失败', message: '视频路径不存在' });
    return;
  }
  if (!filePath.toLowerCase().endsWith('.mp4')) {
    showToast({ type: 'warning', title: '打开失败', message: '视频路径无效（非 .mp4 文件）' });
    return;
  }
  fetch('/api/player/play', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath })
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      showToast({ type: 'error', title: '打开失败', message: data.error });
    }
  })
  .catch(e => showToast({ type: 'error', title: '打开失败', message: e.message || '网络错误' }));
}