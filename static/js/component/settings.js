// 设置页组件

// 默认配置值（与后端 _EnvConfig 对齐）
const SETTINGS_DEFAULTS = {
  wx_download_dir: '下载',
  wx_status_interval: 5,
  log_level: 'INFO',
  max_concurrent: 5,
  doc_sync_interval: 60,
};

// 表单元素 ID → 配置 key 映射
const SETTINGS_MAP = {
  settingDownloadDir: 'wx_download_dir',
  settingStatusInterval: 'wx_status_interval',
  settingLogLevel: 'log_level',
  settingMaxConcurrent: 'max_concurrent',
  settingDocSyncInterval: 'doc_sync_interval',
};

function loadSettings() {
  // 从后端拉取当前配置并填充表单
  fetch('/api/service/config')
    .then(r => r.json())
    .then(data => {
      if (data && typeof data === 'object') {
        fillSettingsForm(data);
      }
    })
    .catch(() => {
      // 后端不可达时用默认值
      fillSettingsForm({});
    });
}

function fillSettingsForm(config) {
  for (const [elemId, key] of Object.entries(SETTINGS_MAP)) {
    const el = document.getElementById(elemId);
    if (!el) continue;

    const val = config[key] !== undefined ? config[key] : SETTINGS_DEFAULTS[key];

    if (el.type === 'checkbox') {
      el.checked = val === true || val === 'true' || val === 1;
    } else {
      el.value = val;
    }
  }
}

function collectSettingsFromForm() {
  const result = {};
  for (const [elemId, key] of Object.entries(SETTINGS_MAP)) {
    const el = document.getElementById(elemId);
    if (!el) continue;

    if (el.type === 'checkbox') {
      result[key] = el.checked;
    } else if (el.type === 'number') {
      result[key] = parseInt(el.value, 10);
    } else {
      result[key] = el.value;
    }
  }
  return result;
}

function saveSettings() {
  const values = collectSettingsFromForm();
  const saveBtn = document.getElementById('btnSaveSettings');

  if (saveBtn && saveBtn.disabled) return;

  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中...';
  }

  // 将前端轮询间隔即时生效
  if (values.wx_status_interval && values.wx_status_interval > 0) {
    // 使用 State.service 管理轮询间隔
    if (typeof State !== 'undefined' && State.service && typeof State.service.setStatusInterval === 'function') {
      State.service.setStatusInterval(values.wx_status_interval * 1000);
    }
  }

  // 收集需要保存到后端的配置（所有可持久化配置项）
  const backendValues = {};
  if (values.max_concurrent) backendValues.max_concurrent = values.max_concurrent;
  if (values.doc_sync_interval) backendValues.doc_sync_interval = values.doc_sync_interval;
  if (values.wx_status_interval) backendValues.wx_status_interval = values.wx_status_interval;
  if (values.wx_download_dir) backendValues.wx_download_dir = values.wx_download_dir;
  if (values.log_level) backendValues.log_level = values.log_level;

  if (Object.keys(backendValues).length > 0) {
    fetch('/api/service/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(backendValues),
    })
    .then(r => r.json())
    .then(data => {
      if (data.code === 0) {
        // 保存成功后弹出重启确认弹窗
        showRestartConfirmDialog();
      } else {
        showToast({ type: 'error', title: '保存失败', message: data.msg });
      }
    })
    .catch(() => {
      showToast({ type: 'error', title: '保存失败', message: '网络错误' });
    })
    .finally(() => {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = '保存设置';
      }
    });
  } else {
    showToast({ type: 'success', title: '设置已保存', message: '轮询间隔已更新' });
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = '保存设置';
    }
  }
}

/**
 * 显示重启确认弹窗
 */
function showRestartConfirmDialog() {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.id = 'restartConfirmOverlay';
  overlay.innerHTML = `
    <div class="dialog-box">
      <div class="dialog-title">配置已保存</div>
      <div class="dialog-content">
        <p>部分配置需重启应用后生效，是否立即重启？</p>
      </div>
      <div class="dialog-buttons">
        <button class="btn-dialog" id="dlgCancel">取消</button>
        <button class="btn-dialog primary" id="dlgConfirm">确定</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // 取消按钮
  overlay.querySelector('#dlgCancel').addEventListener('click', () => {
    overlay.remove();
  });

  // 确定按钮 - 显示关闭中遮罩，然后关闭应用
  overlay.querySelector('#dlgConfirm').addEventListener('click', () => {
    overlay.remove();
    showClosingOverlay();
    closeApplication();
  });
}

/**
 * 显示关闭中遮罩
 */
function showClosingOverlay() {
  const overlay = document.createElement('div');
  overlay.className = 'closing-overlay';
  overlay.innerHTML = `
    <div class="closing-spinner"></div>
    <div class="closing-text" id="closingText">正在关闭</div>
  `;
  document.body.appendChild(overlay);

  // 动态点动画：正在关闭. → 正在关闭.. → 正在关闭... → 正在关闭
  const textEl = document.getElementById('closingText');
  let dotCount = 0;
  const dotInterval = setInterval(() => {
    dotCount = (dotCount + 1) % 4;
    textEl.textContent = '正在关闭' + '.'.repeat(dotCount);
  }, 400);

  // 清理 interval（虽然关闭后进程退出，但保持代码完整）
  overlay.dataset.dotInterval = dotInterval;
}

/**
 * 关闭应用
 */
function closeApplication() {
  // pywebview 环境
  if (window.pywebview && window.pywebview.api && window.pywebview.api.destroy) {
    window.pywebview.api.destroy();
  } else {
    // 浏览器环境 - 尝试关闭窗口
    window.close();
  }
}

function resetSettings() {
  fillSettingsForm(SETTINGS_DEFAULTS);
  showToast({ type: 'info', title: '已恢复默认', message: '点击保存后生效' });
}

async function selectDownloadFolder() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.select_folder) {
    try {
      const result = await window.pywebview.api.select_folder();
      if (result && result.success && result.path) {
        document.getElementById('settingDownloadDir').value = result.path;
      } else if (result && !result.success && result.message !== '已取消选择') {
        showToast({ type: 'error', title: '选择失败', message: result.message });
      }
    } catch (e) {
      console.error('[selectDownloadFolder] 异常:', e);
      showToast({ type: 'error', title: '选择失败', message: e.message || '未知错误' });
    }
  } else {
    showToast({ type: 'warning', title: '不支持', message: '文件夹选择仅在桌面客户端中可用，请手动输入路径' });
  }
}
