// ==================== 响应式渲染器 ====================
//
// 核心思想：订阅 State 变化，智能判断是否需要更新 DOM
// 解决问题：视频状态改变时，当前 Tab 的 UI 不能实时响应
//
// 数据流：SSE → State.updateStatus() → State.emit('videos:status') → ReactiveRenderer
//

var ReactiveRenderer = {
  // 当前视图状态
  _currentTab: 'all',              // all | downloading | downloaded | pending
  _currentVideoType: 'short_video', // short_video | live_replay
  _currentAuthor: null,             // { username, id, nickname }
  _initialized: false,

  // ==================== 初始化 ====================

  init: function() {
    if (this._initialized) return;
    this._initialized = true;

    var self = this;

    // 订阅视频状态变化
    State.on('videos:status', function(e) {
      self._onVideoStatusChange(e);
    });

    // 订阅任务添加（新任务插入时需要重新渲染"正在下载"tab）
    State.on('tasks:add', function(e) {
      self._onTaskAdd(e);
    });

    // 订阅任务进度变化
    State.on('tasks:update', function(e) {
      self._onTaskProgressChange(e);
    });

    // 订阅任务完成
    State.on('tasks:complete', function(e) {
      self._onTaskComplete(e);
    });

    // 订阅任务取消
    State.on('tasks:cancel', function(e) {
      self._onTaskCancel(e);
    });

  },

  // ==================== 公共 API ====================

  // 设置当前视图状态（由 Tab 切换调用）
  setCurrentView: function(tab, videoType, author) {
    this._currentTab = tab || 'all';
    this._currentVideoType = videoType || 'short_video';
    if (author) this._currentAuthor = author;

  },

  // 刷新当前视图（从 State 重新渲染）
  refreshCurrentView: function() {
    if (!this._currentAuthor) return;

    var username = this._currentAuthor.username;
    var videos = State.videos.getAuthorVideos(username);

    // 过滤当前类型
    var filtered = videos.filter(function(v) {
      return (v.video_type || 'short_video') === this._currentVideoType;
    }.bind(this));

    // 调用现有渲染函数
    if (typeof renderVideoList === 'function') {
      renderVideoList(filtered, this._currentTab);
    }

    // 更新统计
    this._updateAllStats(username);
  },

  // ==================== 事件处理 ====================

  _onVideoStatusChange: function(e) {
    var videoId = e.videoId;
    var video = e.video;
    var changes = e.changes;
    var username = e.username;


    // 1. 更新所有 Tab 统计（无论当前在哪个 Tab）
    this._updateAllStats(username);

    // 2. 判断是否需要更新 DOM
    if (!this._shouldRender(video)) {
      return;
    }

    // 3. 更新 DOM
    this._updateVideoRow(video, changes);

    // 4. 如果是从"待下载"变为"已下载"，显示 Toast
    if (changes.downloaded && !changes.downloaded.old && changes.downloaded.new) {
      this._showCompletionToast(video);

      // 如果当前在"正在下载" Tab，从列表中移除（带动画）
      if (this._currentTab === 'downloading') {
        this._removeFromListWithAnimation(videoId);
      }
    }
  },

  _onTaskAdd: function(e) {
    var tasks = e.tasks;
    if (!tasks || tasks.length === 0) return;

    // 如果当前在"正在下载"tab，需要重新渲染视频列表
    if (this._currentTab === 'downloading') {
      this.refreshCurrentView();
    }
  },

  _onTaskProgressChange: function(e) {
    var changes = e.changes;
    if (!changes || changes.length === 0) return;

    // "全部"和"已下载"tab 的进度更新由 updateSingleVideoProgress（链路A）负责
    // ReactiveRenderer 不再参与，避免两条链路互相覆盖导致速度/大小信息丢失
    if (this._currentTab === 'all' || this._currentTab === 'downloaded') {
      return;
    }

    changes.forEach(function(change) {
      var taskId = change.id;
      var task = State.tasks.get(taskId);
      if (!task) return;

      var videoId = task.video_id;
      if (!videoId) return;

      // 更新进度条（如果视频在当前视图）
      var video = State.videos.get(State.videos.getAuthorByVideoId(videoId), videoId);
      if (video && this._shouldRender(video)) {
        this._updateProgressUI(videoId, task);
      }
    }.bind(this));
  },

  _onTaskComplete: function(e) {
    var taskId = e.taskId;
    var data = e.data;
    var videoId = data.video_id;


    // 更新视频状态
    if (videoId) {
      State.videos.updateStatus(videoId, {
        downloaded: true,
        download_path: data.download_path || ''
      });
    }
  },

  _onTaskCancel: function(e) {
    var taskId = e.taskId;
    var task = State.tasks.get(taskId);

    var videoId = task ? task.video_id : null;

    // 从 _activeTasks 移除
    if (typeof _activeTasks !== 'undefined') {
      _activeTasks = _activeTasks.filter(function(t) { return t.id !== taskId; });
    }

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

    // 如果当前在"正在下载"tab，刷新列表
    if (this._currentTab === 'downloading') {
      this.refreshCurrentView();
    }
  },

  // ==================== 渲染判断 ====================

  _shouldRender: function(video) {
    if (!video) return false;

    var videoType = video.video_type || 'short_video';

    // 类型过滤：必须匹配当前类型
    if (videoType !== this._currentVideoType) {
      return false;
    }

    // 作者过滤：必须匹配当前作者
    if (this._currentAuthor) {
      var username = State.videos.getAuthorByVideoId(video.id);
      if (username !== this._currentAuthor.username) {
        return false;
      }
    }

    // Tab 过滤
    switch (this._currentTab) {
      case 'downloading':
        return !video.downloaded && this._isTaskActive(video.id);
      case 'downloaded':
        return video.downloaded;
      case 'pending':
        return !video.downloaded && !this._isTaskActive(video.id);
      default: // 'all'
        return true;
    }
  },

  _isTaskActive: function(videoId) {
    var task = State.tasks.getByVideoId(videoId);
    return task && task.status !== 'done' && task.status !== 'error' && task.status !== 'completed';
  },

  // ==================== DOM 更新 ====================

  _updateVideoRow: function(video, changes) {
    var row = document.querySelector('.video-row[data-id="' + video.id + '"]');
    if (!row) {
      return;
    }

    var badge = row.querySelector('.video-status-badge');
    if (!badge) return;

    // 更新下载状态
    if (changes.downloaded) {
      if (changes.downloaded.new) {
        // 变为已下载
        badge.className = 'video-status-badge downloaded';
        badge.dataset.path = video.download_path || '';
        badge.textContent = '已下载';
        badge.onclick = video.download_path ? function(e) {
          e.stopPropagation();
          if (typeof openVideo === 'function') openVideo(video.download_path);
        } : null;

        row.classList.remove('downloading');

        // 添加播放按钮
        if (video.download_path && !row.querySelector('.video-open-btn')) {
          var openBtn = document.createElement('button');
          openBtn.className = 'video-open-btn';
          openBtn.dataset.path = video.download_path;
          openBtn.title = '打开视频';
          openBtn.textContent = '▶';
          openBtn.onclick = function(e) {
            e.stopPropagation();
            if (typeof openVideo === 'function') openVideo(this.dataset.path);
          };
          row.appendChild(openBtn);
        }
      } else {
        // 变为未下载
        badge.className = 'video-status-badge pending';
        badge.textContent = '待下载';
        badge.onclick = null;
        row.classList.remove('downloading');

        // 移除播放按钮
        var openBtn = row.querySelector('.video-open-btn');
        if (openBtn) openBtn.remove();
      }
    }
  },

  _updateProgressUI: function(videoId, task) {
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    if (!row) return;

    var badge = row.querySelector('.video-status-badge');
    if (!badge) return;

    var pct = task.percent || 0;
    var dlStr = typeof formatFileSize === 'function' ? formatFileSize(task.downloaded || 0) || '--' : '--';
    var szStr = typeof formatFileSize === 'function' ? formatFileSize(task.size || 0) || '--' : '--';
    var speed = task.speed > 0 && typeof formatFileSize === 'function' ? formatFileSize(task.speed) + '/s' : '--';

    if (badge.classList.contains('downloading')) {
      // 快速路径：只更新数字
      var pctEl = badge.querySelector('.progress-percent');
      if (pctEl) pctEl.textContent = pct + '%';
      var fill = badge.querySelector('.progress-fill');
      if (fill) fill.style.width = pct + '%';
      badge.title = dlStr + '/' + szStr + ' · ' + speed;
    } else {
      // 慢速路径：切换为下载中状态
      badge.className = 'video-status-badge downloading';
      badge.title = dlStr + '/' + szStr + ' · ' + speed;
      var hasSpeed = task.speed > 0;
      badge.innerHTML =
        '<div class="download-header">' +
          '<span class="progress-percent">' + pct + '%</span>' +
          '<button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload(\'' + task.id + '\')" aria-label="取消下载">×</button>' +
        '</div>' +
        '<div class="progress-bar" role="progressbar" aria-valuenow="' + pct + '" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" style="width:' + pct + '%"></div></div>' +
        '<div class="download-stats">' +
          '<span class="stat-size">' + dlStr + '/' + szStr + '</span>' +
          '<span class="stat-divider"></span><span class="stat-speed' + (hasSpeed ? '' : ' muted') + '">' + speed + '</span>' +
        '</div>';
      row.classList.add('downloading');
    }
  },

  // ==================== 统计更新 ====================

  _updateAllStats: function(username) {
    if (!username) return;

    var stats = State.videos.getStatsByType(username);

    // 更新头部统计
    this._updateHeaderStats(stats);

    // 更新 Tab 标签数字
    this._updateTabLabels(stats);

    // 更新作者卡片统计（如果在首页）
    this._updateAuthorCardStats(username, stats);
    // 更新全局进度条
    if (typeof updateAuthorGlobalProgress === 'function') {
      updateAuthorGlobalProgress();
    }
  },

  _updateHeaderStats: function(stats) {
    var shortVideoEl = document.getElementById('authorShortVideo');
    var replayEl = document.getElementById('authorReplay');
    var downloadedEl = document.getElementById('authorDownloaded');

    if (shortVideoEl) shortVideoEl.textContent = stats.short_video.total;
    if (replayEl) replayEl.textContent = stats.live_replay.total;

    // downloaded 显示 "已下载/总数" 格式，与 updateAuthorStatsByType() 保持一致
    var downloadedCount = this._currentVideoType === 'live_replay'
      ? stats.live_replay.downloaded
      : stats.short_video.downloaded;
    var totalForType = this._currentVideoType === 'live_replay'
      ? stats.live_replay.total
      : stats.short_video.total;
    if (downloadedEl) downloadedEl.textContent = downloadedCount + '/' + totalForType;
  },

  _updateTabLabels: function(stats) {
    // 不再显示 Tab 数量标注，保持原始文本
    var tabs = document.querySelectorAll('.video-tab');
    tabs.forEach(function(tab) {
      var baseText = tab.dataset.baseText;
      if (!baseText) {
        baseText = tab.textContent.replace(/\s*\(\d+\)/, '').trim();
        tab.dataset.baseText = baseText;
      }
      tab.textContent = baseText;
    });
  },

  _updateAuthorCardStats: function(username, stats) {
    var total = stats.total;
    var downloaded = stats.downloaded;
    var pending = total - downloaded;
    var progress = total > 0 ? Math.round((downloaded / total) * 100) : 0;

    // 更新作者卡片（如果在首页）
    var card = document.querySelector('.author-card[onclick*="' + username + '"]');
    if (card) {
      var statItems = card.querySelectorAll('.stat-item .value');
      if (statItems[0]) statItems[0].textContent = stats.short_video.downloaded + '/' + stats.short_video.total;
      if (statItems[1]) statItems[1].textContent = stats.live_replay.downloaded + '/' + stats.live_replay.total;

      var progressFill = card.querySelector('.author-progress-fill');
      if (progressFill) progressFill.style.width = progress + '%';
      var progressText = card.querySelector('.author-progress-text');
      if (progressText) progressText.textContent = progress + '% 完成';
    }

    // 更新列表视图
    var listItem = document.querySelector('.author-list-item[data-username="' + username + '"]');
    if (listItem) {
      var nums = listItem.querySelectorAll('.author-list-stats .num');
      if (nums[0]) nums[0].textContent = stats.short_video.downloaded + '/' + stats.short_video.total;
      if (nums[1]) nums[1].textContent = stats.live_replay.downloaded + '/' + stats.live_replay.total;

      var progressFill = listItem.querySelector('.author-list-progress-fill');
      if (progressFill) progressFill.style.width = progress + '%';
      var percent = listItem.querySelector('.author-list-percent');
      if (percent) percent.textContent = progress + '%';
    }
  },

  // ==================== Toast 和动画 ====================

  _showCompletionToast: function(video) {
    if (typeof showToast === 'function') {
      showToast({
        type: 'success',
        title: '下载完成',
        message: video.title || '视频已下载完成',
        duration: 3000
      });
    }
  },

  _removeFromListWithAnimation: function(videoId) {
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    if (!row) return;

    // 添加淡出动画
    row.style.transition = 'opacity 0.3s, transform 0.3s';
    row.style.opacity = '0';
    row.style.transform = 'translateX(-20px)';

    setTimeout(function() {
      if (typeof _removeRowAndUpdatePagination === 'function') {
        _removeRowAndUpdatePagination(row);
      } else {
        row.remove();
      }
    }, 300);
  }
};

// 自动初始化
if (typeof State !== 'undefined') {
  ReactiveRenderer.init();
}
