// 视频操作数据处理

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

  const videos = _authorVideosData[_currentAuthor.username]?.videos || {};
  const selectedIds = Array.from(_selectedVideos);

  // 检测非待下载状态的视频（已下载 + 正在下载）
  const nonPendingIds = selectedIds.filter(id => {
    const video = videos[id];
    if (!video) return false;
    const isDownloading = _activeTasks.some(t => t.video_id === id && t.status !== 'done' && t.status !== 'completed' && t.status !== 'error');
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

  const data = await fetchWithErrorHandling('/api/task/batch-create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_ids: pendingIds
    })
  }, '添加下载');

  if (data && data.code === 0) {
    const count = data.data?.count || 0;
    showToast({ type: 'success', title: '添加成功', message: `已将 ${count} 个视频添加到下载队列` });

    await refreshActiveTasks();

    const currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
    if (currentFilter === 'pending') {
      pendingIds.forEach(videoId => {
        var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
        if (row) _removeRowAndUpdatePagination(row);
      });
    } else {
      updateDownloadStatus(pendingIds);
    }

    clearSelection();
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

  const videos = _authorVideosData[_currentAuthor.username]?.videos || {};
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
        const authorData = _authorVideosData[_currentAuthor.username];
        if (authorData && authorData.videos) {
          selectedArr.forEach(id => {
            delete authorData.videos[id];
          });
          const videos = Object.values(authorData.videos);
          updateVideoListIncremental(videos);
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

function downloadAllPending() {
  if (!_currentAuthor) return;

  const videos = _authorVideosData[_currentAuthor.username]?.videos || {};
  const pendingVideos = Object.entries(videos)
    .filter(([id, v]) => !v.downloaded);

  if (pendingVideos.length === 0) {
    showToast({ type: 'warning', title: '没有待下载视频', message: '当前作者所有视频已下载' });
    return;
  }

  const shortVideoPending = pendingVideos.filter(([id, v]) => (v.video_type || 'short_video') === 'short_video').length;
  const replayPending = pendingVideos.filter(([id, v]) => v.video_type === 'live_replay').length;

  showDownloadRangeDialog({
    shortVideoPending,
    replayPending,
    nickname: _currentAuthor.nickname
  }, (selectedType) => {
    let filteredIds;
    if (selectedType === 'short_video') {
      filteredIds = pendingVideos
        .filter(([id, v]) => (v.video_type || 'short_video') === 'short_video')
        .map(([id, v]) => id);
    } else if (selectedType === 'live_replay') {
      filteredIds = pendingVideos
        .filter(([id, v]) => v.video_type === 'live_replay')
        .map(([id, v]) => id);
    } else {
      filteredIds = pendingVideos.map(([id, v]) => id);
    }

    if (filteredIds.length === 0) {
      showToast({ type: 'warning', title: '没有待下载视频', message: '所选类型没有待下载视频' });
      return;
    }

    const username = _currentAuthor.username;
    confirmDownloadAllPending(username, filteredIds);
  });
}

async function confirmDownloadAllPending(username, pendingIds) {
  var btn = document.querySelector('.btn-primary[onclick="downloadAllPending()"]');
  if (btn && btn.disabled) return;
  if (btn) { btn.disabled = true; btn.textContent = '添加中...'; }

  showToast({ type: 'success', title: '正在添加', message: `正在添加 ${pendingIds.length} 个视频到下载队列...` });

  const data = await fetchWithErrorHandling('/api/task/batch-create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_ids: pendingIds })
  }, '批量添加下载');

  if (data && data.code === 0) {
    const count = data.data?.count || 0;
    showToast({ type: 'success', title: '添加成功', message: `已将 ${count} 个视频添加到下载队列` });

    await refreshActiveTasks();

    const currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
    if (currentFilter === 'pending') {
      pendingIds.forEach(videoId => {
        var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
        if (row) _removeRowAndUpdatePagination(row);
      });
    } else {
      updateDownloadStatus(pendingIds);
    }
  }

  if (btn) { btn.disabled = false; btn.textContent = '全部下载'; }
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
  await refreshAfterVideoChange();

  const authorData = _authorVideosData[_currentAuthor.username];
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

  // 先从 _activeTasks 获取 videoId（HTTP 请求是异步的，_activeTasks 可能被其他刷新覆盖）
  var task = _activeTasks.find(t => t.id === taskId);
  var videoId = task ? task.video_id : null;

  // 立即标记为已取消（在 HTTP 请求发出前就标记，防止竞态）
  if (typeof _cancelledTaskIds !== 'undefined') {
    _cancelledTaskIds[taskId] = true;
    setTimeout(function() { delete _cancelledTaskIds[taskId]; }, 30000);
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

function updateCancelStatus(taskId, videoId) {
  // 使用 State.tasks.cancel 触发响应式更新
  State.tasks.cancel(taskId);

  // 更新视频行 UI
  if (videoId) {
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    if (row) {
      var badge = row.querySelector('.video-status-badge');
      if (badge) {
        badge.className = 'video-status-badge pending';
        badge.textContent = '待下载';
      }
      row.classList.remove('downloading');
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