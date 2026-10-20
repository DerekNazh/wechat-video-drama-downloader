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
  // 自动模式（生命周期跟随程序）：服务由程序启动/关闭自动管理，无需人工启停。
  const btn = event?.target?.closest('button') || event?.target;
  if (!btn) return;

  var svc = typeof State !== 'undefined' && State.service ? State.service : null;
  var goOnline = svc && typeof svc.isGoOnline === 'function' ? svc.isGoOnline() : _goOnline;
  showToast({
    type: 'info',
    title: goOnline ? '服务运行中' : '服务自动启动中',
    message: '服务跟随程序自动运行，微信连上即自动下载，无需手动操作'
  });
  return;
}

async function toggleOneClickMonitor() {
  // 自动模式（生命周期跟随程序）：监控由程序启动/关闭自动管理，无需人工启停。
  var svc = typeof State !== 'undefined' && State.service ? State.service : null;
  var monitorRunning = svc && typeof svc.isMonitorRunning === 'function'
    ? svc.isMonitorRunning() : _monitorRunning;
  if (monitorRunning) {
    showToast({ type: 'info', title: '自动监控中', message: '监控跟随程序自动运行，微信连上即自动下载，无需手动操作' });
  } else {
    showToast({ type: 'info', title: '等待自动监控', message: '监控即将自动启动（等待微信连接），无需手动操作' });
  }
  return;
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
