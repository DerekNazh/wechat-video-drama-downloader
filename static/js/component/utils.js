// 通用工具函数

async function fetchWithErrorHandling(url, options = {}, actionName = '操作') {
  const controller = new AbortController();
  const timeoutId = setTimeout(function() { controller.abort(); }, 60000);

  try {
    const res = await fetch(url, Object.assign({}, options, { signal: controller.signal }));
    clearTimeout(timeoutId);
    if (!res.ok) {
      var msg = 'HTTP ' + res.status;
      try {
        var body = await res.json();
        // 503: detail 可能是 {"code": -1, "msg": "..."} 或 {"detail": {"code": -1, "msg": "..."}}
        var detail = body.detail || body;
        if (detail.msg) msg = detail.msg;
        else if (detail.message) msg = detail.message;
      } catch(_) {}
      showToast({ type: 'error', title: actionName + '失败', message: msg });
      return null;
    }
    return await res.json();
  } catch (e) {
    clearTimeout(timeoutId);
    if (e.name === 'AbortError') {
      showToast({ type: 'error', title: actionName + '超时', message: '请求超过 60 秒未响应' });
    } else {
      showToast({ type: 'error', title: actionName + '失败', message: e.message || '网络错误' });
    }
    return null;
  }
}

async function toggleService(event) {
  const btn = event?.target?.closest('button') || event?.target;
  if (!btn) return;

  const wasOnline = _goOnline;

  // 停止服务时，检查是否有活跃下载任务
  if (wasOnline) {
    var activeCount = _activeTasks.filter(function(t) {
      return t.status !== 'done' && t.status !== 'completed' && t.status !== 'error' && t.status !== 'failed';
    }).length;
    if (activeCount > 0) {
      var confirmed = await showStopServiceConfirm(activeCount);
      if (!confirmed) return;
    }
  }

  const url = wasOnline ? '/api/service/stop' : '/api/service/start';

  btn.disabled = true;
  btn.textContent = wasOnline ? '停止中...' : '启动中...';

  try {
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();
    if (data.code === 0) {
      // API 返回成功 = 操作已完成，立刻更新 UI
      _goOnline = !wasOnline;
      State.service.setGoOnline(_goOnline);

      // 立刻调一次 status 获取真实微信连接状态
      fetch("/api/service/status")
        .then(r => r.json())
        .then(s => {
          if (s.code === 0) {
            updateStatusFromPoll({
              service_online: s.data.service_online,
              wechat_connected: s.data.wechat_connected,
              monitor_running: _monitorRunning,
              today_count: s.data.today_count || 0,
              today_downloaded: s.data.today_downloaded || 0,
              total_videos: s.data.total_videos || 0,
            });
          }
        })
        .catch(() => {});

      showToast({
        type: 'success',
        title: wasOnline ? '服务已停止' : '服务已启动',
        message: data.msg || ''
      });
    } else {
      showToast({ type: 'error', title: '操作失败', message: data.msg || '' });
    }
  } catch (e) {
    showToast({ type: 'error', title: '操作失败', message: e.message });
  }

  btn.disabled = false;
  btn.textContent = _goOnline ? '■ 停止' : '▶ 启动';
}

async function toggleOneClickMonitor() {
  var svc = typeof State !== 'undefined' && State.service ? State.service : null;
  var goOnline = svc && typeof svc.isGoOnline === 'function' ? svc.isGoOnline() : _goOnline;
  var wechatOk = svc && typeof svc.isWechatConnected === 'function' ? svc.isWechatConnected() : false;

  if (!goOnline) {
    showToast({ type: 'warning', title: '服务未启动', message: '微信视频号后端服务未启动，请先启动服务' });
    return;
  }
  if (!wechatOk) {
    showToast({ type: 'warning', title: '微信未连接', message: '微信客户端未连接，请先打开微信并登录' });
    return;
  }

  try {
    if (_monitorRunning) {
      const res = await apiFetch('/api/monitor/stop', { method: 'POST' });
      const data = await res.json();
      if (data.code === 0) {
        _monitorRunning = false;
        State.service.setMonitorRunning(false);
        // 立刻调一次 status 获取真实微信状态
        fetch("/api/service/status")
          .then(r => r.json())
          .then(s => {
            if (s.code === 0) {
              updateStatusFromPoll({
                service_online: s.data.service_online,
                wechat_connected: s.data.wechat_connected,
                monitor_running: false,
                today_count: s.data.today_count || 0,
                today_downloaded: s.data.today_downloaded || 0,
                total_videos: s.data.total_videos || 0,
              });
            }
          })
          .catch(() => {});
        showToast({ type: 'success', title: '监控已停止' });
      }
    } else {
      const res = await apiFetch('/api/monitor/start', { method: 'POST' });
      const data = await res.json();
      if (data.code === 0) {
        _monitorRunning = true;
        State.service.setMonitorRunning(true);
        // 立刻调一次 status 获取真实微信状态
        fetch("/api/service/status")
          .then(r => r.json())
          .then(s => {
            if (s.code === 0) {
              updateStatusFromPoll({
                service_online: s.data.service_online,
                wechat_connected: s.data.wechat_connected,
                monitor_running: true,
                today_count: s.data.today_count || 0,
                today_downloaded: s.data.today_downloaded || 0,
                total_videos: s.data.total_videos || 0,
              });
            }
          })
          .catch(() => {});
        showToast({ type: 'success', title: '监控已启动' });
      }
    }
  } catch (e) {
    showToast({ type: 'error', title: '操作失败', message: e.message });
  }
}

function showStopServiceConfirm(activeCount) {
  return new Promise(function(resolve) {
    document.querySelectorAll('.dialog-overlay').forEach(function(d) { d.remove(); });

    var overlay = document.createElement('div');
    overlay.className = 'dialog-overlay';
    overlay.dataset.closable = 'true';
    overlay.innerHTML =
      '<div class="dialog-box">' +
        '<div class="dialog-icon-wrapper">' +
          '<div class="dialog-icon info">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
              '<path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>' +
            '</svg>' +
          '</div>' +
        '</div>' +
        '<div class="dialog-title">确认停止服务</div>' +
        '<div class="dialog-content">' +
          '<p>当前有 <strong>' + activeCount + '</strong> 个下载任务正在进行中</p>' +
          '<p class="dialog-hint">停止后任务将暂停，重启服务后可自动恢复</p>' +
        '</div>' +
        '<div class="dialog-buttons">' +
          '<button class="btn-dialog secondary" id="stopCancelBtn">取消</button>' +
          '<button class="btn-dialog primary" id="stopConfirmBtn" style="background:var(--danger)">停止服务</button>' +
        '</div>' +
      '</div>';

    document.body.appendChild(overlay);

    overlay.querySelector('#stopCancelBtn').addEventListener('click', function() {
      closeDialog(overlay);
      resolve(false);
    });
    overlay.querySelector('#stopConfirmBtn').addEventListener('click', function() {
      closeDialog(overlay);
      resolve(true);
    });
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay && overlay.dataset.closable === 'true') {
        closeDialog(overlay);
        resolve(false);
      }
    });
  });
}
