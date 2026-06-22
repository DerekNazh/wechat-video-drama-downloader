// 视频搜索与选择组件
function searchVideos() {
  _currentPageNum = 1;
  refreshVideoList();
}

function toggleVideoSelect(id) {
  if (_selectedVideos.has(id)) {
    _selectedVideos.delete(id);
  } else {
    _selectedVideos.add(id);
  }

  const row = document.querySelector(`.video-row[data-id="${id}"]`);
  if (row) {
    row.classList.toggle('selected', _selectedVideos.has(id));
  }

  updateSelectionBar();
}

function selectAllVideos() {
  const username = _currentAuthor?.username;
  if (!username) return;

  var videos = Object.values(_authorVideosData[username]?.videos || {});

  // 构造与 renderVideoList 相同的筛选条件
  var downloadingIds = new Set();
  _activeTasks.forEach(function(task) {
    var videoId = task.video_id || '';
    if (videoId && task.status !== 'done' && task.status !== 'completed' && task.status !== 'error' && task.status !== 'failed') {
      downloadingIds.add(videoId);
    }
  });

  var currentFilter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
  var filtered = getFilteredVideos(videos, currentFilter, downloadingIds);

  // 只选当前筛选结果中的视频
  filtered.forEach(function(video) {
    _selectedVideos.add(video.id);
  });

  // 同步 DOM 视觉状态
  document.querySelectorAll('.video-row').forEach(row => {
    const id = row.dataset.id;
    if (id && _selectedVideos.has(id)) {
      row.classList.add('selected');
      const cb = row.querySelector('.video-checkbox');
      if (cb) cb.setAttribute('aria-checked', 'true');
    }
  });
  updateSelectionBar();
}

function clearSelection() {
  _selectedVideos.clear();
  document.querySelectorAll('.video-row.selected').forEach(row => {
    row.classList.remove('selected');
    const cb = row.querySelector('.video-checkbox');
    if (cb) cb.setAttribute('aria-checked', 'false');
  });
  updateSelectionBar();
}

// 键盘操作支持：checkbox 区域按 Enter/Space 切换选中
document.addEventListener('keydown', function(e) {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('video-checkbox')) {
    e.preventDefault();
    const row = e.target.closest('.video-row');
    const id = row?.dataset?.id;
    if (id) toggleVideoSelect(id);
  }
});

function updateSelectionBar() {
  const bar = document.getElementById('selectionBar');
  if (!bar) return;

  const count = _selectedVideos.size;
  if (count === 0) {
    bar.classList.remove('visible');
    return;
  }

  bar.classList.add('visible');
  const countEl = bar.querySelector('#selectedCount');
  if (countEl) countEl.textContent = count;

  const infoEl = bar.querySelector('.selection-info');
  if (!infoEl) return;

  const videos = _authorVideosData[_currentAuthor?.username]?.videos || {};
  let shortVideoCount = 0;
  let replayCount = 0;

  _selectedVideos.forEach(id => {
    const video = videos[id];
    if (video) {
      if ((video.video_type || 'short_video') === 'short_video') {
        shortVideoCount++;
      } else if (video.video_type === 'live_replay') {
        replayCount++;
      }
    }
  });

  let typeBreakdownHtml = '';
  if (shortVideoCount > 0 && replayCount > 0) {
    typeBreakdownHtml = ` <span class="type-tag short-video">${shortVideoCount} 短视频</span> + <span class="type-tag replay">${replayCount} 回放</span>`;
  } else if (shortVideoCount > 0) {
    typeBreakdownHtml = ` <span class="type-tag short-video">${shortVideoCount} 短视频</span>`;
  } else if (replayCount > 0) {
    typeBreakdownHtml = ` <span class="type-tag replay">${replayCount} 回放</span>`;
  }

  infoEl.innerHTML = `已选 <strong id="selectedCount">${count}</strong> 个${typeBreakdownHtml}`;
}