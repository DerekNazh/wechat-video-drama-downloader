var BatchProgressDialog = (function() {
  var _overlay = null;
  var _cancelled = false;
  var _closing = false;
  var _onCancel = null;

  function el(id) {
    return document.getElementById(id);
  }

  function open(options) {
    _cancelled = false;
    _onCancel = options.onCancel || null;

    var total = options.total || 0;
    var title = options.title || '批量添加下载';

    if (_overlay) _overlay.remove();

    _overlay = document.createElement('div');
    _overlay.className = 'dialog-overlay';
    _overlay.id = 'batchProgressDialog';
    _overlay.innerHTML =
      '<div class="dialog-box">' +
        '<div class="dialog-icon-wrapper">' +
          '<div class="dialog-icon info">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
              '<path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>' +
            '</svg>' +
          '</div>' +
        '</div>' +
        '<div class="dialog-title">' + title + '</div>' +
        '<div class="dialog-content">' +
          '<div class="batch-progress-info">' +
            '<span id="batchProgressCount">0</span>/<span id="batchProgressTotal">' + total + '</span> 个视频已添加到下载队列' +
          '</div>' +
          '<div class="batch-progress-bar-wrap">' +
            '<div class="batch-progress-bar" id="batchProgressBar"><div class="batch-progress-fill" id="batchProgressFill"></div></div>' +
            '<span class="batch-progress-percent" id="batchProgressPercent">0%</span>' +
          '</div>' +
          '<div class="batch-progress-detail" id="batchProgressDetail"></div>' +
        '</div>' +
        '<div class="dialog-buttons">' +
          '<button class="btn-dialog danger" id="batchCancelBtn">停止添加</button>' +
        '</div>' +
      '</div>';

    document.body.appendChild(_overlay);

    _overlay.querySelector('#batchCancelBtn').addEventListener('click', function() {
      _cancelled = true;
      var btn = _overlay.querySelector('#batchCancelBtn');
      if (btn) { btn.disabled = true; btn.textContent = '正在停止...'; }
      if (_onCancel) _onCancel();
    });

    _overlay.addEventListener('click', function(e) {
      // 点击遮罩不关闭进度对话框
    });
  }

  function update(count, total, detail) {
    var countEl = el('batchProgressCount');
    var totalEl = el('batchProgressTotal');
    var fillEl = el('batchProgressFill');
    var percentEl = el('batchProgressPercent');
    var detailEl = el('batchProgressDetail');

    if (countEl) countEl.textContent = count;
    if (totalEl) totalEl.textContent = total;

    var pct = total > 0 ? Math.round((count / total) * 100) : 0;
    if (fillEl) fillEl.style.width = pct + '%';
    if (percentEl) percentEl.textContent = pct + '%';
    if (detailEl) detailEl.textContent = detail || '';
  }

  function close(result) {
    if (!_overlay || _closing) return;
    _closing = true;

    // 用户主动取消（选择阶段点取消）→ 立即关闭，不显示完成态
    if (!result) {
      _cleanup();
      return;
    }

    var failCount = result.failed || 0;
    var successCount = result.success || 0;
    var isCancelled = result.cancelled;

    var dialogBox = _overlay.querySelector('.dialog-box');
    if (!dialogBox) { _cleanup(); return; }

    var iconClass, iconSvg, titleText, summaryText;
    if (isCancelled) {
      iconClass = 'warning';
      iconSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>';
      titleText = '已停止';
      summaryText = successCount + ' 个已添加, ' + failCount + ' 个失败, 剩余已跳过';
    } else if (failCount > 0) {
      iconClass = 'warning';
      iconSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>';
      titleText = '部分完成';
      summaryText = successCount + ' 个成功, ' + failCount + ' 个失败';
    } else {
      iconClass = 'success';
      iconSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
      titleText = '添加完成';
      summaryText = '已将 ' + successCount + ' 个视频添加到下载队列';
    }

    // 替换对话框内容为完成态
    dialogBox.innerHTML =
      '<div class="dialog-icon-wrapper">' +
        '<div class="dialog-icon ' + iconClass + ' batch-done-icon">' +
          iconSvg +
        '</div>' +
      '</div>' +
      '<div class="dialog-title">' + titleText + '</div>' +
      '<div class="dialog-content">' +
        '<p class="batch-done-summary">' + summaryText + '</p>' +
      '</div>';

    // 2s 后淡出消失
    setTimeout(function() {
      if (!_overlay) return;
      _overlay.style.transition = 'opacity 0.3s ease';
      _overlay.style.opacity = '0';
      setTimeout(function() { _cleanup(); }, 300);
    }, 2000);
  }

  function _cleanup() {
    if (_overlay) {
      _overlay.remove();
      _overlay = null;
    }
    _closing = false;
    _cancelled = false;
  }

  function isCancelled() {
    return _cancelled;
  }

  function isOpen() {
    return _overlay !== null;
  }

  function switchToProgress(options) {
    if (!_overlay || _closing) return;
    _cancelled = false;
    _closing = false;
    _onCancel = options.onCancel || null;

    var total = options.total || 0;
    var title = options.title || '批量添加下载';
    var dialogBox = _overlay.querySelector('.dialog-box');
    if (!dialogBox) return;

    dialogBox.innerHTML =
      '<div class="dialog-icon-wrapper">' +
        '<div class="dialog-icon info">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
            '<path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>' +
          '</svg>' +
        '</div>' +
      '</div>' +
      '<div class="dialog-title">' + title + '</div>' +
      '<div class="dialog-content">' +
        '<div class="batch-progress-info">' +
          '<span id="batchProgressCount">0</span>/<span id="batchProgressTotal">' + total + '</span> 个视频已添加到下载队列' +
        '</div>' +
        '<div class="batch-progress-bar-wrap">' +
          '<div class="batch-progress-bar" id="batchProgressBar"><div class="batch-progress-fill" id="batchProgressFill"></div></div>' +
          '<span class="batch-progress-percent" id="batchProgressPercent">0%</span>' +
        '</div>' +
        '<div class="batch-progress-detail" id="batchProgressDetail"></div>' +
      '</div>' +
      '<div class="dialog-buttons">' +
        '<button class="btn-dialog danger" id="batchCancelBtn">停止添加</button>' +
      '</div>';

    _overlay.querySelector('#batchCancelBtn').addEventListener('click', function() {
      _cancelled = true;
      var btn = _overlay.querySelector('#batchCancelBtn');
      if (btn) { btn.disabled = true; btn.textContent = '正在停止...'; }
      if (_onCancel) _onCancel();
    });
  }

  return {
    open: open,
    update: update,
    close: close,
    isCancelled: isCancelled,
    isOpen: isOpen,
    switchToProgress: switchToProgress
  };
})();
