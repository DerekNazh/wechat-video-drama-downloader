/**
 * 腾讯文档监控组件
 *
 * 功能：
 * 1. 启动/停止文档监控
 * 2. 实时状态展示（运行中/上次同步时间/新增数）
 * 3. SSE 事件驱动更新
 * 4. 错误弹窗（按 error_code 差异化）
 */

const DocSyncMonitor = (() => {
  let _running = false;
  let _statusTimer = null;

  function el(id) {
    return document.getElementById(id);
  }

  function init() {
    loadStatus();
  }

  function loadStatus() {
    fetch('/api/monitor/doc-sync/status')
      .then(r => r.json())
      .then(data => {
        if (data.code === 0 && data.data) {
          updateUI(data.data);
        }
      })
      .catch(() => {});
  }

  function updateUI(status) {
    _running = status.running || false;

    // 更新导入卡片激活状态（所有页面都需要）
    setImportCardActive(_running);

    // 更新设置页面的 UI（仅设置页面有这些元素）
    const btn = el('btnDocSyncToggle');
    const desc = el('docSyncStatusDesc');

    if (!btn || !desc) return;

    if (_running) {
      btn.textContent = '停止监控';
      btn.classList.add('btn-danger');
      btn.classList.remove('btn-primary');
      desc.textContent = `运行中 | 间隔 ${status.interval_min || 60} 分钟`;
      if (status.last_sync_at) {
        desc.textContent += ` | 上次同步: ${formatTime(status.last_sync_at)}`;
        updateStatusBar(status.last_sync_at);
      }
      startStatusPoll();
    } else {
      btn.textContent = '启动监控';
      btn.classList.remove('btn-danger');
      btn.classList.add('btn-primary');
      if (status.last_sync_at) {
        desc.textContent = `已停止 | 上次同步: ${formatTime(status.last_sync_at)}`;
      } else {
        desc.textContent = '未启动';
      }
      stopStatusPoll();
    }
  }

  function setImportCardActive(active) {
    const card = el('tencentDocImportCard');
    const indicator = el('monitoringIndicator');
    const stopBtn = el('monitoringStopBtn');
    const existingBar = el('monitoringStatusBar');

    if (!card) return;

    if (active) {
      card.classList.add('monitoring-active');
      if (indicator) indicator.style.display = 'flex';
      if (stopBtn) stopBtn.style.display = 'flex';
      addStatusBar(card);
    } else {
      card.classList.remove('monitoring-active');
      if (indicator) indicator.style.display = 'none';
      if (stopBtn) stopBtn.style.display = 'none';
      if (existingBar) existingBar.remove();
    }
  }

  function checkDependencies() {
    const svc = typeof State !== 'undefined' && State.service ? State.service : null;
    const serviceOnline = svc && typeof svc.isGoOnline === 'function'
      ? !!svc.isGoOnline()
      : false;

    const wechatConnected = svc && typeof svc.isWechatConnected === 'function'
      ? !!svc.isWechatConnected()
      : false;

    return {
      serviceOnline,
      wechatConnected,
      ready: serviceOnline && wechatConnected
    };
  }

  function addStatusBar(card) {
    if (el('monitoringStatusBar')) return;

    const bar = document.createElement('div');
    bar.className = 'monitoring-status-bar';
    bar.id = 'monitoringStatusBar';
    bar.innerHTML = `
      <span class="status-icon"><span class="status-dot"></span>实时监控</span>
      <span class="status-time" id="monitoringLastSync">上次同步: 刚启动</span>
    `;

    card.parentElement.style.position = 'relative';
    card.parentElement.appendChild(bar);
  }

  function updateStatusBar(lastSyncAt) {
    const timeEl = el('monitoringLastSync');
    if (!timeEl) return;
    const timeText = formatTime(lastSyncAt);
    timeEl.textContent = `上次同步: ${timeText}`;
  }

  function toggleDocSync() {
    if (_running) {
      stop();
    } else {
      start();
    }
  }

  function start() {
    const docUrl = el('settingDocSyncUrl')?.value?.trim() || '';
    const clientId = el('settingDocSyncClientId')?.value?.trim() || '';
    const accessToken = el('settingDocSyncAccessToken')?.value?.trim() || '';
    const openId = el('settingDocSyncOpenId')?.value?.trim() || '';
    const interval = parseInt(el('settingDocSyncInterval')?.value) || 60;

    if (!docUrl) {
      showToast({ type: 'warning', title: '请填写文档 URL', message: '请输入腾讯文档的分享链接' });
      return;
    }
    if (!clientId || !accessToken || !openId) {
      showToast({ type: 'warning', title: '请填写完整凭证', message: 'Client ID、Access Token、Open ID 均为必填' });
      return;
    }

    const dep = checkDependencies();
    if (!dep.ready) {
      const reasons = [];
      if (!dep.serviceOnline) reasons.push('微信视频号后端服务未启动');
      if (!dep.wechatConnected) reasons.push('微信客户端未连接');
      showToast({ type: 'warning', title: '前置条件未满足', message: reasons.join('，') + '，请先检查连接状态' });
      return;
    }

    const btn = el('btnDocSyncToggle');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '启动中...';
    }

    fetch('/api/monitor/doc-sync/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_url: docUrl,
        client_id: clientId,
        access_token: accessToken,
        openid: openId,
        interval_min: interval,
      }),
    })
    .then(r => r.json())
    .then(data => {
      if (data.code === 0) {
        showToast({ type: 'success', title: '监控已启动', message: data.msg });
        loadStatus();
      } else {
        handleApiError(data);
      }
    })
    .catch(e => {
      showToast({ type: 'error', title: '启动失败', message: e.message || '网络错误' });
    })
    .finally(() => {
      if (btn) {
        btn.disabled = false;
      }
    });
  }

  function startFromPanel() {
    const docUrl = el('tencentDocUrl')?.value?.trim() || '';
    const clientId = el('tencentClientId')?.value?.trim() || '';
    const accessToken = el('tencentAccessToken')?.value?.trim() || '';
    const openId = el('tencentOpenId')?.value?.trim() || '';
    const interval = parseInt(el('settingDocSyncInterval')?.value) || 60;

    if (!docUrl) {
      showToast({ type: 'warning', title: '请填写文档 URL', message: '请输入腾讯文档的分享链接' });
      return;
    }
    if (!clientId || !accessToken || !openId) {
      showToast({ type: 'warning', title: '请填写完整凭证', message: 'Client ID、Access Token、Open ID 均为必填' });
      return;
    }

    const dep = checkDependencies();
    if (!dep.ready) {
      const reasons = [];
      if (!dep.serviceOnline) reasons.push('微信视频号后端服务未启动');
      if (!dep.wechatConnected) reasons.push('微信客户端未连接');
      showToast({ type: 'warning', title: '前置条件未满足', message: reasons.join('，') + '，请先检查连接状态' });
      return;
    }

    const btn = el('btnStartDocSyncMonitor');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '启动中...';
    }

    fetch('/api/monitor/doc-sync/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_url: docUrl,
        client_id: clientId,
        access_token: accessToken,
        openid: openId,
        interval_min: interval,
      }),
    })
    .then(r => r.json())
    .then(data => {
      if (data.code === 0) {
        showToast({ type: 'success', title: '监控已启动', message: data.msg });
        loadStatus();
        if (typeof hideTencentDocImport === 'function') {
          hideTencentDocImport();
        }
      } else {
        handleApiError(data);
      }
    })
    .catch(e => {
      showToast({ type: 'error', title: '启动失败', message: e.message || '网络错误' });
    })
    .finally(() => {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '实时监控';
      }
    });
  }

  function stop() {
    const btn = el('btnDocSyncToggle');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '停止中...';
    }

    fetch('/api/monitor/doc-sync/stop', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.code === 0) {
        showToast({ type: 'info', title: '监控已停止', message: data.msg });
        loadStatus();
      } else {
        handleApiError(data);
      }
    })
    .catch(e => {
      showToast({ type: 'error', title: '停止失败', message: e.message || '网络错误' });
    })
    .finally(() => {
      if (btn) btn.disabled = false;
    });
  }

  function handleApiError(data) {
    const errorCode = data.error_code || '';
    const msg = data.msg || '未知错误';
    const severity = data.severity || 'fatal';

    // fatal 级别错误使用弹窗，其他使用 toast
    const useDialog = severity === 'fatal';

    switch (errorCode) {
      case 'DOC_URL_INVALID':
        showToast({ type: 'error', title: 'URL 格式错误', message: msg });
        break;
      case 'DOC_CREDENTIAL_MISSING':
        showToast({ type: 'error', title: '凭证缺失', message: '请填写完整的 Client ID、Access Token、Open ID' });
        break;
      case 'DOC_AUTH_FAILED':
      case 'DOC_TOKEN_MISMATCH':
        showToast({ type: 'error', title: '认证失败', message: msg + '，请检查凭证是否正确' });
        break;
      case 'DOC_QUOTA_EXCEEDED':
        showToast({ type: 'warning', title: 'API 配额用完', message: msg + '，请稍后重试' });
        break;
      case 'DOC_MULTI_SHEET':
        showErrorDialog({
          title: '文档格式错误',
          message: msg,
          suggestion: '请打开腾讯文档，删除多余的子表，只保留一个子表后重试'
        });
        break;
      case 'DOC_NO_SHEET':
        showErrorDialog({
          title: '文档无子表',
          message: msg,
          suggestion: '请打开腾讯文档，创建至少一个子表后重试'
        });
        break;
      case 'DOC_PERMISSION_DENIED':
        showErrorDialog({
          title: '无访问权限',
          message: msg,
          suggestion: '请检查文档分享权限，确保已开启"任何人可查看"或"任何人可编辑"'
        });
        break;
      case 'DOC_NOT_FOUND':
        showErrorDialog({
          title: '文档不存在',
          message: msg,
          suggestion: '请检查文档 URL 是否正确，或文档是否已被删除'
        });
        break;
      case 'DOC_PARSE_ERROR':
        showToast({ type: 'warning', title: '数据解析失败', message: msg });
        break;
      case 'DOC_SYNC_ALREADY_RUNNING':
        showToast({ type: 'info', title: '已在运行', message: msg });
        loadStatus();
        break;
      case 'WX_BACKEND_OFFLINE':
        showErrorDialog({
          title: '微信后端服务未启动',
          message: msg,
          suggestion: '请先启动微信视频号后端服务（Go 后端）'
        });
        break;
      case 'WX_NOT_CONNECTED':
        showErrorDialog({
          title: '微信未连接',
          message: msg,
          suggestion: '请打开微信客户端并登录，确保微信视频号功能可用'
        });
        break;
      default:
        if (useDialog) {
          showErrorDialog({ title: '操作失败', message: msg });
        } else {
          showToast({ type: 'error', title: '操作失败', message: msg });
        }
    }
  }

  /**
   * 显示 Windows 11 风格错误弹窗
   * @param {Object} options - 弹窗选项
   * @param {string} options.title - 标题
   * @param {string} options.message - 错误信息
   * @param {string} [options.suggestion] - 解决建议
   */
  function showErrorDialog(options) {
    const { title = '错误', message = '', suggestion = '' } = options;

    // 移除已存在的弹窗
    const existing = document.querySelector('.error-dialog-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'error-dialog-overlay';
    overlay.innerHTML = `
      <div class="error-dialog-box">
        <div class="error-dialog-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <div class="error-dialog-title">${title}</div>
        <div class="error-dialog-message">${message}</div>
        ${suggestion ? `
          <div class="error-dialog-suggestion">
            <svg viewBox="0 0 20 20" fill="currentColor" class="suggestion-icon">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
            </svg>
            <span>${suggestion}</span>
          </div>
        ` : ''}
        <div class="error-dialog-buttons">
          <button class="error-dialog-btn primary" id="errorDialogOk">确定</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // 点击确定按钮关闭
    overlay.querySelector('#errorDialogOk').addEventListener('click', () => {
      overlay.classList.add('out');
      setTimeout(() => overlay.remove(), 200);
    });

    // 点击遮罩关闭
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.classList.add('out');
        setTimeout(() => overlay.remove(), 200);
      }
    });

    // ESC 关闭
    const escHandler = (e) => {
      if (e.key === 'Escape') {
        overlay.classList.add('out');
        setTimeout(() => overlay.remove(), 200);
        document.removeEventListener('keydown', escHandler);
      }
    };
    document.addEventListener('keydown', escHandler);
  }

  function handleSSEProgress(data) {
    if (data.import_type !== 'doc_sync') return;

    if (data.error_code) {
      handleApiError(data);
      // fatal 错误后端会停止监控，刷新 UI 状态
      if (data.severity === 'fatal') {
        loadStatus();
      }
      return;
    }

    if (data.new_rows && data.new_rows > 0) {
      showToast({
        type: 'success',
        title: '文档同步完成',
        message: `发现 ${data.new_rows} 个新作者，成功 ${data.imported || 0} 个`,
      });
    }

    loadStatus();

    // 刷新作者列表
    if (typeof refreshAuthors === 'function' && data.imported > 0) {
      refreshAuthors();
    }
  }

  function startStatusPoll() {
    stopStatusPoll();
    _statusTimer = setInterval(loadStatus, 60000);
  }

  function stopStatusPoll() {
    if (_statusTimer) {
      clearInterval(_statusTimer);
      _statusTimer = null;
    }
  }

  function formatTime(isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      const now = new Date();
      const diff = Math.floor((now - d) / 1000);
      if (diff < 60) return '刚刚';
      if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
      if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoStr;
    }
  }

  function isRunning() {
    return _running;
  }

  return { init, toggleDocSync, handleSSEProgress, loadStatus, startFromPanel, setImportCardActive, updateStatusBar, isRunning };
})();

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', () => {
  DocSyncMonitor.init();
});

// 全局函数绑定（HTML onclick 用）
function toggleDocSync() {
  DocSyncMonitor.toggleDocSync();
}

function startDocSyncFromPanel() {
  DocSyncMonitor.startFromPanel();
}
