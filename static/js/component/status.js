// 状态面板更新组件
// 缓存上一次的状态值，只在值变化时才更新 DOM（最小渲染原则）
let _lastStatus = {
  service_online: null,
  wechat_connected: null,
  monitor_running: null,
  today_count: null,
  today_downloaded: null,
  total_videos: null,
};

// 离线防抖定时器（与后端 MonitorService 3s 防抖对齐，避免瞬断时任务闪烁为 paused）
let _offlineDebounceTimer = null;

function updateStatusFromPoll(status) {
  if (!status) return;

  // 记录变化前的值（必须在更新 _lastStatus 之前读取）
  var prevServiceOnline = _lastStatus.service_online;
  var prevWechatConnected = _lastStatus.wechat_connected;
  var prevMonitorRunning = _lastStatus.monitor_running;
  var prevTodayCount = _lastStatus.today_count;
  var prevTodayDownloaded = _lastStatus.today_downloaded;
  var prevTotalVideos = _lastStatus.total_videos;

  // 更新缓存（只更新传入的字段）
  if (status.service_online !== undefined) _lastStatus.service_online = status.service_online;
  if (status.wechat_connected !== undefined) _lastStatus.wechat_connected = status.wechat_connected;
  if (status.monitor_running !== undefined) _lastStatus.monitor_running = status.monitor_running;
  if (status.today_count !== undefined) _lastStatus.today_count = status.today_count;
  if (status.today_downloaded !== undefined) _lastStatus.today_downloaded = status.today_downloaded;
  if (status.total_videos !== undefined) _lastStatus.total_videos = status.total_videos;

  // 计算是否有变化（基于更新前的值）
  var serviceChanged = status.service_online !== undefined && status.service_online !== prevServiceOnline;
  var wechatChanged = status.wechat_connected !== undefined && status.wechat_connected !== prevWechatConnected;
  var monitorChanged = status.monitor_running !== undefined && status.monitor_running !== prevMonitorRunning;
  var todayCountChanged = status.today_count !== undefined && status.today_count !== prevTodayCount;
  var todayDownloadedChanged = status.today_downloaded !== undefined && status.today_downloaded !== prevTodayDownloaded;
  var totalChanged = status.total_videos !== undefined && status.total_videos !== prevTotalVideos;

  // 如果没有任何变化，跳过渲染
  if (!serviceChanged && !wechatChanged && !monitorChanged &&
      !todayCountChanged && !todayDownloadedChanged && !totalChanged) {
    return;
  }

  // 更新全局状态（用于其他逻辑判断）
  if (status.service_online !== undefined) {
    var wasOnline = _goOnline;
    _goOnline = status.service_online;
    State.service.setGoOnline(status.service_online);

    // 服务离线时，3s 防抖后再标记 paused（与后端 MonitorService 对齐，避免瞬断闪烁）
    if (wasOnline && !_goOnline) {
      // 只在首次离线时启动防抖，不重置已有计时器（避免 onerror 反复重置导致任务永不 paused）
      if (!_offlineDebounceTimer) {
        // 闭包捕获当前页面状态，避免 3s 后用户已切换页面导致渲染到错误作者
        var _snapshotAuthor = _currentAuthor;
        var _snapshotPage = _currentPage;
        _offlineDebounceTimer = setTimeout(function() {
        _offlineDebounceTimer = null;
        _activeTasks.forEach(function(t) {
          if (t.status === 'running' || t.status === 'wait') {
            State.tasks.update(t.video_id, { status: 'paused', speed: 0 });
          }
        });
        _activeTasks = State.tasks.all().filter(function(t) { return t.status !== 'done' && t.status !== 'completed' && t.status !== 'error' && t.status !== 'failed'; });
        // 触发视频列表渲染，让 paused badge 显示出来
        if (_snapshotAuthor && _snapshotPage === 'author') {
          var videos = Object.values(_authorVideosData[_snapshotAuthor.username]?.videos || {});
          if (typeof updateVideoListIncremental === 'function' && videos.length > 0) {
            updateVideoListIncremental(videos);
          }
        }
        if (typeof showToast === 'function') {
          var pausedCount = _activeTasks.filter(function(t) { return t.status === 'paused'; }).length;
          var msg = 'Go 服务已离线';
          if (pausedCount > 0) msg += '，' + pausedCount + ' 个任务暂停';
          msg += ' — 请启动Go服务恢复下载';
          showToast({ type: 'warning', title: '服务离线', message: msg });
        }
      }, 3000);
      }
    }
    // 服务恢复在线：取消防抖定时器
    if (!wasOnline && _goOnline) {
      if (_offlineDebounceTimer) {
        clearTimeout(_offlineDebounceTimer);
        _offlineDebounceTimer = null;
      }
      if (typeof showToast === 'function') {
        showToast({ type: 'success', title: '服务恢复', message: 'Go 后端服务已重新上线' });
      }
      // 主动刷新任务列表 + 渲染，让 badge 从 paused 过渡到正确状态
      if (typeof refreshActiveTasks === 'function') {
        refreshActiveTasks();
      }
      if (_currentAuthor && _currentPage === 'author') {
        var videos = Object.values(_authorVideosData[_currentAuthor?.username || '']?.videos || {});
        if (typeof updateVideoListIncremental === 'function' && videos.length > 0) {
          updateVideoListIncremental(videos);
        }
      }
    }
  }

  // Go 服务状态（只在变化时更新）
  if (serviceChanged) {
    const txtService = document.getElementById('txtService');
    const dotService = document.getElementById('dotService');
    if (txtService) {
      txtService.textContent = status.service_online ? '在线' : '离线';
    }
    if (dotService) {
      dotService.className = status.service_online ? 'dot green' : 'dot red';
    }

    // 更新服务按钮文字
    const btnService = document.getElementById('btnService');
    if (btnService) {
      if (status.service_online) {
        btnService.innerHTML = '&#9632; 停止';
      } else {
        btnService.innerHTML = '&#9654; 启动';
      }
    }
  }

  // 微信连接状态（只在变化时更新）
  if (wechatChanged) {
    // 写入 State（供 checkDependencies 等逻辑读取）
    State.service.setWechatConnected(status.wechat_connected);

    const txtWechat = document.getElementById('txtWechat');
    const dotWechat = document.getElementById('dotWechat');
    if (txtWechat) {
      txtWechat.textContent = status.wechat_connected ? '已连接' : '未连接';
    }
    if (dotWechat) {
      dotWechat.className = status.wechat_connected ? 'dot green' : 'dot red';
    }

    if (typeof showToast === 'function') {
      if (!prevWechatConnected && status.wechat_connected) {
        showToast({ type: 'success', title: '微信已连接', message: '微信视频号已成功连接' });
      } else if (prevWechatConnected && !status.wechat_connected) {
        showToast({ type: 'warning', title: '微信已断开', message: '请重新登录微信以恢复下载' });
      }
    }
  }

  // 监控状态（只在变化时更新）
  if (monitorChanged) {
    const txtMonitor = document.getElementById('txtMonitor');
    const dotMonitor = document.getElementById('dotMonitor');
    if (txtMonitor) {
      txtMonitor.textContent = status.monitor_running ? '运行中' : '已停止';
    }
    if (dotMonitor) {
      dotMonitor.className = status.monitor_running ? 'dot green' : 'dot';
    }

    // 同步监控按钮状态
    if (typeof updateMonitorButton === 'function') {
      updateMonitorButton(status.monitor_running);
    }
  }

  // 视频统计数字（只在变化时更新）
  if (todayCountChanged) {
    const txtTodayCount = document.getElementById('txtTodayCount');
    if (txtTodayCount) {
      txtTodayCount.textContent = status.today_count || 0;
      txtTodayCount.classList.remove('bounce');
      void txtTodayCount.offsetWidth;
      txtTodayCount.classList.add('bounce');
    }
  }
  if (todayDownloadedChanged) {
    const txtTodayDownloaded = document.getElementById('txtTodayDownloaded');
    if (txtTodayDownloaded) {
      txtTodayDownloaded.textContent = status.today_downloaded || 0;
      txtTodayDownloaded.classList.remove('bounce');
      void txtTodayDownloaded.offsetWidth;
      txtTodayDownloaded.classList.add('bounce');
    }
  }
  if (totalChanged) {
    const txtTotalVideos = document.getElementById('txtTotalVideos');
    if (txtTotalVideos) {
      txtTotalVideos.textContent = status.total_videos || 0;
      txtTotalVideos.classList.remove('bounce');
      void txtTotalVideos.offsetWidth;
      txtTotalVideos.classList.add('bounce');
    }
  }

  // 更新抽屉摘要（统计变化时更新）
  if (todayCountChanged || todayDownloadedChanged || monitorChanged || serviceChanged || wechatChanged) {
    // 使用当前缓存的状态构建完整数据
    updateDrawerSummary({
      service_online: _lastStatus.service_online,
      wechat_connected: _lastStatus.wechat_connected,
      monitor_running: _lastStatus.monitor_running,
      today_count: _lastStatus.today_count,
      today_downloaded: _lastStatus.today_downloaded,
    });
  }
}

function updateDrawerSummary(data) {
  const dot = document.getElementById('fabDot');
  const icon = document.getElementById('fabIcon');
  const btn = document.getElementById('fabBtn');
  if (!dot || !btn) return;

  // 保存 FAB 当前位置（防止任何渲染操作意外重置拖动位置）
  var savedLeft = btn.style.left;
  var savedTop = btn.style.top;
  var savedRight = btn.style.right;
  var savedBottom = btn.style.bottom;

  const tc = data.today_count || 0;
  const td = data.today_downloaded || 0;

  // Update badge with download count
  var badge = document.getElementById('fabBadge');
  var downloadingCount = (State.tasks && State.tasks.all()) ? State.tasks.all().filter(function(t) { return t.status === 'running'; }).length : 0;
  if (badge) {
    var prevCount = parseInt(badge.textContent) || 0;
    if (downloadingCount > 0) {
      badge.textContent = downloadingCount;
      badge.style.display = 'flex';
      // 弹跳动画
      if (downloadingCount !== prevCount) {
        badge.classList.remove('bounce');
        void badge.offsetWidth;
        badge.classList.add('bounce');
      }
    } else {
      badge.style.display = 'none';
    }
  }

  // 添加/移除 downloading 类（呼吸动画）
  if (downloadingCount > 0 && data.service_online) {
    btn.classList.add('downloading');
  } else {
    btn.classList.remove('downloading');
  }

  // Update FAB appearance based on status
  // 使用 classList 代替 className 赋值，避免覆盖 drag 位置等状态
  btn.classList.remove('offline', 'wechat-off');
  if (data.monitor_running) {
    dot.className = 'fab-dot green';
  } else if (data.service_online && data.wechat_connected) {
    dot.className = 'fab-dot yellow';
  } else if (data.service_online) {
    dot.className = 'fab-dot yellow';
    btn.classList.add('wechat-off');
  } else {
    dot.className = 'fab-dot red';
    btn.classList.add('offline');
  }

  // 恢复 FAB 位置（防止 classList 操作触发重排导致位置丢失）
  if (savedLeft) btn.style.left = savedLeft;
  if (savedTop) btn.style.top = savedTop;
  if (savedRight) btn.style.right = savedRight;
  if (savedBottom) btn.style.bottom = savedBottom;
}

function toggleFabPanel() {
  var panel = document.getElementById('fabPanel');
  if (!panel) return;
  var isOpen = panel.classList.contains('open');
  if (isOpen) {
    panel.classList.remove('open');
    // 关闭时恢复 right 偏移（匹配当前宽度）
    var w = panel.offsetWidth;
    panel.style.right = -w + 'px';
  } else {
    panel.classList.add('open');
    panel.style.right = '0';
  }
}

// =========================================
// 悬浮球拖动
// =========================================
var _fabDragging = false;
var _fabDragMoved = false;
var _fabDragStartX = 0;
var _fabDragStartY = 0;
var _fabOffsetX = 0;
var _fabOffsetY = 0;

(function initFabDrag() {
  var btn = document.getElementById('fabBtn');
  if (!btn) return;

  // 从 localStorage 恢复位置
  var saved = null;
  try { saved = JSON.parse(localStorage.getItem('fabPos')); } catch(e) {}
  if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
    _fabOffsetX = saved.x;
    _fabOffsetY = saved.y;
    btn.style.left = _fabOffsetX + 'px';
    btn.style.top = _fabOffsetY + 'px';
    btn.style.right = 'auto';
    btn.style.bottom = 'auto';
  }

  btn.addEventListener('mousedown', function(e) {
    _fabDragging = true;
    _fabDragMoved = false;
    _fabDragStartX = e.clientX;
    _fabDragStartY = e.clientY;
    btn.classList.add('dragging');
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!_fabDragging) return;
    var dx = e.clientX - _fabDragStartX;
    var dy = e.clientY - _fabDragStartY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      _fabDragMoved = true;
    }
    var rect = btn.getBoundingClientRect();
    var newX = rect.left + dx;
    var newY = rect.top + dy;
    // 边界约束
    newX = Math.max(0, Math.min(window.innerWidth - 48, newX));
    newY = Math.max(0, Math.min(window.innerHeight - 48, newY));
    btn.style.left = newX + 'px';
    btn.style.top = newY + 'px';
    btn.style.right = 'auto';
    btn.style.bottom = 'auto';
    _fabDragStartX = e.clientX;
    _fabDragStartY = e.clientY;
  });

  document.addEventListener('mouseup', function() {
    if (!_fabDragging) return;
    _fabDragging = false;
    btn.classList.remove('dragging');
    // 保存位置
    var rect = btn.getBoundingClientRect();
    try { localStorage.setItem('fabPos', JSON.stringify({ x: rect.left, y: rect.top })); } catch(e) {}
  });
})();

// 覆盖 onclick：拖动时不触发面板
(function overrideFabClick() {
  var btn = document.getElementById('fabBtn');
  if (!btn) return;
  btn.onclick = null;
  btn.addEventListener('click', function(e) {
    if (_fabDragMoved) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    toggleFabPanel();
  });
})();

// 点击面板外部关闭
document.addEventListener('click', function(e) {
  var panel = document.getElementById('fabPanel');
  var btn = document.getElementById('fabBtn');
  if (panel && panel.classList.contains('open') &&
      !panel.contains(e.target) && !btn.contains(e.target)) {
    panel.classList.remove('open');
    var w = panel.offsetWidth;
    panel.style.right = -w + 'px';
  }
});

// Escape 键关闭面板
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    var panel = document.getElementById('fabPanel');
    if (panel && panel.classList.contains('open')) {
      panel.classList.remove('open');
      var w = panel.offsetWidth;
      panel.style.right = -w + 'px';
    }
  }
});

// =========================================
// 抽屉可调宽度拖拽
// =========================================
(function initDrawerResize() {
  var handle = document.getElementById('drawerResizeHandle');
  var panel = document.getElementById('fabPanel');
  if (!handle || !panel) return;

  var _resizing = false;
  var _startX = 0;
  var _startWidth = 0;
  var MIN_WIDTH = 320;
  var MAX_WIDTH = 900;

  // 从 localStorage 恢复宽度
  var savedWidth = null;
  try { savedWidth = parseInt(localStorage.getItem('drawerWidth'), 10); } catch(e) {}
  if (savedWidth && savedWidth >= MIN_WIDTH && savedWidth <= MAX_WIDTH) {
    panel.style.width = savedWidth + 'px';
    panel.style.right = -(savedWidth) + 'px';
  }

  handle.addEventListener('mousedown', function(e) {
    e.preventDefault();
    e.stopPropagation();
    _resizing = true;
    _startX = e.clientX;
    _startWidth = panel.offsetWidth;
    handle.classList.add('active');
    panel.classList.add('resizing');
  });

  document.addEventListener('mousemove', function(e) {
    if (!_resizing) return;
    // 向左拖 = 宽度增大（鼠标远离右边缘）
    var dx = _startX - e.clientX;
    var newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, _startWidth + dx));
    panel.style.width = newWidth + 'px';
  });

  document.addEventListener('mouseup', function() {
    if (!_resizing) return;
    _resizing = false;
    handle.classList.remove('active');
    panel.classList.remove('resizing');
    try { localStorage.setItem('drawerWidth', panel.offsetWidth); } catch(e) {}
  });
})();
