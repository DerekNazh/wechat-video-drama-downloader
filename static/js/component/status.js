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

    // 服务离线时，将 running/wait 任务标记为 paused
    if (wasOnline && !_goOnline) {
      _activeTasks = _activeTasks.map(function(t) {
        return (t.status === 'running' || t.status === 'wait')
          ? Object.assign({}, t, { status: 'paused', speed: 0 })
          : t;
      });
      State.tasks.setAll(_activeTasks);
      // 通知用户服务已离线
      if (typeof showToast === 'function') {
        var pausedCount = _activeTasks.filter(function(t) { return t.status === 'paused'; }).length;
        var msg = 'Go 后端服务已离线';
        if (pausedCount > 0) msg += '，' + pausedCount + ' 个下载任务已暂停';
        showToast({ type: 'warning', title: '服务离线', message: msg });
      }
    }
    // 服务恢复在线
    if (!wasOnline && _goOnline) {
      if (typeof showToast === 'function') {
        showToast({ type: 'success', title: '服务恢复', message: 'Go 后端服务已重新上线' });
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
      dotService.className = status.service_online ? 'dot green' : 'dot';
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
      dotWechat.className = status.wechat_connected ? 'dot green' : 'dot';
    }

    if (typeof showToast === 'function') {
      if (!prevWechatConnected && status.wechat_connected) {
        showToast({ type: 'success', title: '微信已连接', message: '微信视频号已成功连接' });
      } else if (prevWechatConnected && !status.wechat_connected) {
        showToast({ type: 'warning', title: '微信已断开', message: '微信视频号连接已断开' });
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
    if (txtTodayCount) txtTodayCount.textContent = status.today_count || 0;
  }
  if (todayDownloadedChanged) {
    const txtTodayDownloaded = document.getElementById('txtTodayDownloaded');
    if (txtTodayDownloaded) txtTodayDownloaded.textContent = status.today_downloaded || 0;
  }
  if (totalChanged) {
    const txtTotalVideos = document.getElementById('txtTotalVideos');
    if (txtTotalVideos) txtTotalVideos.textContent = status.total_videos || 0;
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
  const dot = document.getElementById('summaryDot');
  const text = document.getElementById('summaryText');
  if (!dot || !text) return;

  const tc = data.today_count || 0;
  const td = data.today_downloaded || 0;

  if (data.monitor_running) {
    dot.className = 'drawer-dot green';
    text.textContent = `监控运行中 | 今日新增${tc} 已下载${td}`;
  } else if (data.service_online && data.wechat_connected) {
    dot.className = 'drawer-dot yellow';
    text.textContent = `服务在线 | 今日新增${tc} 已下载${td}`;
  } else if (data.service_online) {
    dot.className = 'drawer-dot yellow';
    text.textContent = '服务在线 | 微信未连接';
  } else {
    dot.className = 'drawer-dot red';
    text.textContent = '服务离线';
  }
}

let _drawerOpen = true;

function toggleStatusDrawer() {
  _drawerOpen = !_drawerOpen;
  const drawer = document.getElementById('statusDrawer');
  drawer.classList.toggle('open', _drawerOpen);
}
