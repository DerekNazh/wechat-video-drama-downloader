// 对话框组件
function showDeleteConfirmDialog(count, downloadedCount, recordOnlyCount, onCancel, onConfirm) {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';

  let detailHtml = '';
  if (downloadedCount > 0 && recordOnlyCount > 0) {
    detailHtml = `<p class="dialog-detail">其中 <strong>${downloadedCount}</strong> 个已下载（含视频文件），<strong>${recordOnlyCount}</strong> 个仅记录。删除将同时移除视频文件和数据库记录</p>`;
  } else if (downloadedCount > 0) {
    detailHtml = `<p class="dialog-detail">全部已下载，删除将同时移除视频文件和数据库记录</p>`;
  } else if (recordOnlyCount > 0) {
    detailHtml = `<p class="dialog-detail">全部为未下载记录，仅移除数据库记录</p>`;
  }

  overlay.innerHTML = `
    <div class="dialog-box danger">
      <div class="dialog-icon-wrapper">
        <div class="dialog-icon danger">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
          </svg>
        </div>
      </div>
      <div class="dialog-title">确认删除视频</div>
      <div class="dialog-content">
        <p>确定要删除选中的 <strong>${count}</strong> 个视频吗？</p>
        ${detailHtml}
      </div>
      <div class="dialog-buttons">
        <button class="btn-dialog secondary" id="dlgCancel">取消</button>
        <button class="btn-dialog danger" id="dlgConfirm">删除</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  overlay.querySelector('#dlgCancel').addEventListener('click', () => {
    closeDialog(overlay);
    onCancel && onCancel();
  });

  overlay.querySelector('#dlgConfirm').addEventListener('click', () => {
    closeDialog(overlay);
    onConfirm && onConfirm();
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      closeDialog(overlay);
      onCancel && onCancel();
    }
  });

  var escHandler = (e) => {
    if (e.key === 'Escape') {
      closeDialog(overlay);
      onCancel && onCancel();
    }
  };
  overlay._escHandler = escHandler;
  document.addEventListener('keydown', escHandler);
}

function closeDialog(el) {
  if (!el || el.classList.contains('closing')) return;
  // 清理 Escape 键监听器
  if (el._escHandler) {
    document.removeEventListener('keydown', el._escHandler);
    el._escHandler = null;
  }
  var dialogBox = el.querySelector('.dialog-box');
  el.classList.add('closing');
  if (dialogBox) dialogBox.classList.add('closing');
  setTimeout(function() { el.remove(); }, 200);
}

function showDownloadRangeDialog(options, onConfirm) {
  const { shortVideoPending, replayPending, nickname } = options;
  const total = shortVideoPending + replayPending;

  if (total === 0) {
    showToast({ type: 'warning', title: '没有待下载视频', message: '当前作者所有视频已下载' });
    return;
  }

  const esc = (s) => (s || '').replace(/'/g, "\\'").replace(/"/g, '\\"');

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';

  const shortVideoOptionHtml = shortVideoPending > 0 ? `
    <div class="download-range-option" data-type="short_video">
      <div class="option-radio"></div>
      <div class="option-content">
        <div class="option-title">仅短视频</div>
        <div class="option-desc">${shortVideoPending} 个待下载</div>
      </div>
    </div>
  ` : '';

  const replayOptionHtml = replayPending > 0 ? `
    <div class="download-range-option" data-type="live_replay">
      <div class="option-radio"></div>
      <div class="option-content">
        <div class="option-title">仅直播回放</div>
        <div class="option-desc">${replayPending} 个待下载</div>
      </div>
    </div>
  ` : '';

  overlay.innerHTML = `
    <div class="dialog-box">
      <div class="dialog-icon-wrapper">
        <div class="dialog-icon info">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
          </svg>
        </div>
      </div>
      <div class="dialog-title">下载全部待下载视频 — ${esc(nickname)}</div>
      <div class="dialog-content">
        <p>作者: <strong>${esc(nickname)}</strong></p>
        <p class="dialog-hint">请选择下载范围</p>
        <div class="download-range-options">
          <div class="download-range-option selected" data-type="all">
            <div class="option-radio"></div>
            <div class="option-content">
              <div class="option-title">全部下载</div>
              <div class="option-desc">短视频 + 直播回放，${total} 个</div>
            </div>
          </div>
          ${shortVideoOptionHtml}
          ${replayOptionHtml}
        </div>
      </div>
      <div class="dialog-buttons">
        <button class="btn-dialog secondary" id="dlgCancel">取消</button>
        <button class="btn-dialog primary" id="dlgConfirm">开始下载</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  let selectedType = 'all';

  const optionEls = overlay.querySelectorAll('.download-range-option');
  optionEls.forEach(opt => {
    opt.addEventListener('click', () => {
      optionEls.forEach(o => o.classList.remove('selected'));
      opt.classList.add('selected');
      selectedType = opt.dataset.type;
    });
  });

  overlay.querySelector('#dlgCancel').addEventListener('click', () => closeDialog(overlay));

  overlay.querySelector('#dlgConfirm').addEventListener('click', () => {
    closeDialog(overlay);
    onConfirm && onConfirm(selectedType);
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeDialog(overlay);
  });

  var escHandler = (e) => {
    if (e.key === 'Escape') {
      closeDialog(overlay);
    }
  };
  overlay._escHandler = escHandler;
  document.addEventListener('keydown', escHandler);
}