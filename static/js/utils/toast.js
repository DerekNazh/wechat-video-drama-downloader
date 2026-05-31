// Toast 提示系统
function showToast(options) {
  const { type = 'warning', title = '', message = '', duration = 4000 } = options;

  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const icons = {
    warning: '<svg class="toast-icon warning" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>',
    error: '<svg class="toast-icon error" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>',
    success: '<svg class="toast-icon success" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>'
  };

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    ${icons[type] || icons.warning}
    <div class="toast-content">
      ${title ? `<div class="toast-title">${title}</div>` : ''}
      ${message ? `<div class="toast-message">${message}</div>` : ''}
    </div>
    <button class="toast-close" onclick="this.parentElement.classList.add('out'); setTimeout(() => this.parentElement.remove(), 300)">×</button>
  `;

  container.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => {
      if (toast.parentElement) {
        toast.classList.add('out');
        setTimeout(() => toast.remove(), 300);
      }
    }, duration);
  }
}

// 任务完成 Toast 批量合并（300ms 防抖）
var _completionToastTimer = null;
var _completionToastCount = 0;

function showTaskCompletionToast(videoTitle) {
  _completionToastCount++;

  if (_completionToastTimer) {
    clearTimeout(_completionToastTimer);
  }

  _completionToastTimer = setTimeout(function() {
    if (_completionToastCount === 1) {
      showToast({ type: 'success', title: '下载完成', message: videoTitle });
    } else {
      showToast({ type: 'success', title: '下载完成', message: _completionToastCount + ' 个视频下载完成' });
    }
    _completionToastCount = 0;
    _completionToastTimer = null;
  }, 300);
}
