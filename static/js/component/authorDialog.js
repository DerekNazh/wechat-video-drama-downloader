// 同步对话框状态封装（替代散落的 window.__syncXXX 全局变量）
var SyncDialogState = {
  authorName: null,
  done: false,
  addedCount: 0,
  totalSV: 0,
  totalRP: 0,
  reset: function() {
    this.authorName = null;
    this.done = false;
    this.addedCount = 0;
    this.totalSV = 0;
    this.totalRP = 0;
  }
};

// 作者同步对话框组件
function showSyncOptionsDialog(username, nickname, headUrl, profession, signature, btn) {
  document.querySelectorAll('.dialog-overlay').forEach(d => d.remove());

  const esc = (s) => (s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
  const escHtml = (s) => (s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const defaultDate = new Date();
  defaultDate.setDate(defaultDate.getDate() - 30);
  const dateStr = defaultDate.toISOString().split('T')[0];

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.id = 'syncOptionsDialog';
  overlay.innerHTML = `
    <div class="dialog-box">
      <div class="dialog-icon-wrapper">
        <div class="dialog-icon info">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"/>
          </svg>
        </div>
      </div>
      <div class="dialog-title">添加作者 - 同步视频</div>
      <div class="dialog-content">
        <div class="sync-author-preview">
          ${headUrl ? `<img src="${headUrl}" onerror="this.outerHTML='<div class=\\'avatar-placeholder\\'>?</div>'">` : '<div class="avatar-placeholder">?</div>'}
          <div class="sync-author-info">
            <div class="sync-author-name">${escHtml(nickname)}</div>
            <div class="sync-author-meta">${escHtml(profession) || '视频号作者'}</div>
          </div>
        </div>

        <p style="margin-bottom: 12px;">选择视频同步方式:</p>

        <div class="sync-option-cards">
          <div class="sync-option-card selected" data-mode="date">
            <div class="sync-option-radio"></div>
            <div class="sync-option-info">
              <div class="sync-option-title">按日期同步</div>
              <div class="sync-option-desc">同步指定日期之后发布的所有视频</div>
              <div class="sync-option-input">
                <input type="date" id="syncDateInput" value="${dateStr}" onclick="event.stopPropagation()">
                <div class="input-hint">将同步此日期之后的视频</div>
              </div>
            </div>
          </div>

          <div class="sync-option-card" data-mode="pages">
            <div class="sync-option-radio"></div>
            <div class="sync-option-info">
              <div class="sync-option-title">按页数同步</div>
              <div class="sync-option-desc">同步指定页数内的视频(每页约20个)</div>
              <div class="sync-option-input">
                <input type="number" id="syncPagesInput" value="5" min="1" max="50" onclick="event.stopPropagation()">
                <div class="input-hint">建议 1-10 页，过多可能耗时较长</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="dialog-buttons">
        <button class="btn-dialog secondary" id="dlgCancelBtn">取消</button>
        <button class="btn-dialog primary" id="dlgConfirmBtn">开始同步</button>
      </div>

      <div class="sync-progress" id="syncProgress">
        <div class="sync-step-indicator" id="syncStepIndicator">
          <div class="sync-step" data-step="1"><span class="sync-step-label">准备</span></div>
          <div class="sync-step-line"></div>
          <div class="sync-step" data-step="2"><span class="sync-step-label">短视频</span></div>
          <div class="sync-step-line"></div>
          <div class="sync-step" data-step="3"><span class="sync-step-label">回放</span></div>
          <div class="sync-step-line"></div>
          <div class="sync-step" data-step="4"><span class="sync-step-label">保存</span></div>
        </div>
        <div class="sync-progress-header">
          <div class="sync-progress-spinner"></div>
          <div class="sync-progress-text" id="syncProgressText">正在同步视频...</div>
        </div>
        <div class="sync-progress-count" id="syncProgressCount">已获取 0 个视频</div>
        <div class="sync-progress-stats" id="syncProgressStats">
          <span class="sync-stat-item" id="syncStatSV"><span class="sync-stat-label">已找到短视频</span><span class="sync-stat-num" id="syncStatSVNum">0</span></span>
          <span class="sync-stat-divider"></span>
          <span class="sync-stat-item" id="syncStatRP"><span class="sync-stat-label">回放</span><span class="sync-stat-num" id="syncStatRPNum">0</span></span>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  overlay.dataset.username = username;
  overlay.dataset.nickname = nickname;
  overlay.dataset.headurl = headUrl;
  overlay.dataset.profession = profession;
  overlay.dataset.signature = signature;
  overlay.dataset.btnId = btn ? btn.id : '';

  // 卡片点击切换同步模式（排除 input 点击）
  overlay.querySelectorAll('.sync-option-card').forEach(function(card) {
    card.addEventListener('click', function(e) {
      if (!e.target.closest('input')) {
        selectSyncMode(card.dataset.mode);
      }
    });
  });

  overlay.querySelector('#dlgCancelBtn').addEventListener('click', () => closeDialog(overlay));

  overlay.querySelector('#dlgConfirmBtn').addEventListener('click', () => {
    confirmSyncAuthor(overlay);
  });
}

function selectSyncMode(mode) {
  document.querySelectorAll('.sync-option-card').forEach(card => {
    card.classList.toggle('selected', card.dataset.mode === mode);
  });
}

async function confirmSyncAuthor(overlay) {
  var _syncingAuthorName = overlay.dataset.nickname || '';
  SyncDialogState.reset();
  SyncDialogState.authorName = _syncingAuthorName;

  const username = overlay.dataset.username;
  const nickname = overlay.dataset.nickname;
  const headUrl = overlay.dataset.headurl;
  const profession = overlay.dataset.profession;
  const signature = overlay.dataset.signature;
  const btnId = overlay.dataset.btnId;

  const selectedCard = document.querySelector('.sync-option-card.selected');
  const syncMode = selectedCard?.dataset.mode || 'date';

  let syncDate = '';
  let syncPages = 5;

  if (syncMode === 'date') {
    syncDate = document.getElementById('syncDateInput')?.value || '';
  } else {
    syncPages = parseInt(document.getElementById('syncPagesInput')?.value || '5');
  }

  const progressEl = document.getElementById('syncProgress');
  const progressCountEl = document.getElementById('syncProgressCount');
  const confirmBtn = document.getElementById('dlgConfirmBtn');
  const cancelBtn = document.getElementById('dlgCancelBtn');
  const dialogContent = overlay.querySelector('.dialog-content');
  const dialogButtons = overlay.querySelector('.dialog-buttons');

  if (dialogContent) { dialogContent.classList.add('fade-out'); }
  if (dialogButtons) { dialogButtons.classList.add('fade-out'); }
  setTimeout(function() {
    if (dialogContent) dialogContent.style.display = 'none';
    if (dialogButtons) dialogButtons.style.display = 'none';
  }, 200);
  progressEl.style.display = 'block';
  progressEl.classList.add('fade-in');
  confirmBtn.disabled = true;
  // 允许用户在同步期间关闭对话框（同步仍在后台运行）
  cancelBtn.disabled = false;
  cancelBtn.textContent = '关闭';
  cancelBtn.title = '同步将在后台继续，完成后会自动刷新';

  const result = await addAuthor(username, nickname, headUrl, profession, signature, syncMode, syncDate, syncPages);

  // SSE done 可能已经触发关闭（通过 _onSyncDoneCloseDialog）
  if (SyncDialogState.done) {
    // SSE 已关闭对话框，只需做按钮状态 + 刷新
    _finishSyncSuccess(btnId, nickname);
    return;
  }

  if (result?.success || result?.added) {
    // SSE done 还没到（兜底：HTTP 先返回），延迟关闭让用户看到完成状态
    var progressTextEl = document.getElementById('syncProgressText');
    if (progressTextEl) progressTextEl.textContent = '同步完成';
    var progressCountEl2 = document.getElementById('syncProgressCount');
    if (progressCountEl2) progressCountEl2.textContent = '新增 ' + (result.added || 0) + ' 个视频';

    await new Promise(r => setTimeout(r, 1200));
    SyncDialogState.authorName = null;
    closeDialog(overlay);
    _finishSyncSuccess(btnId, nickname);
  } else {
    if (dialogContent) { dialogContent.style.display = ''; dialogContent.classList.remove('fade-out'); }
    if (dialogButtons) { dialogButtons.style.display = ''; dialogButtons.classList.remove('fade-out'); }
    progressEl.style.display = 'none';
    progressEl.classList.remove('fade-in');
    confirmBtn.disabled = false;
    cancelBtn.disabled = false;
    cancelBtn.textContent = '取消';
    cancelBtn.title = '';
    SyncDialogState.reset();
    showToast({ type: 'error', title: '添加失败', message: result?.message || '未知错误' });
  }
}

function _finishSyncSuccess(btnId, nickname) {
  var addedCount = SyncDialogState.addedCount || 0;
  SyncDialogState.reset();

  if (btnId) {
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.classList.add('added');
      btn.disabled = true;
      btn.textContent = '已添加';
    }
  }

  refreshAuthors();
  navigateTo('home');
  if (addedCount > 0) {
    showToast({ type: 'success', title: '添加成功', message: `已添加 "${nickname}"，新增 ${addedCount} 个视频` });
  } else {
    showToast({ type: 'success', title: '作者已添加', message: `"${nickname}" 暂无符合条件的新视频` });
  }
}

async function addAuthor(username, nickname, headUrl, profession, signature, syncMode = 'date', syncDate = '', syncPages = 5) {
  try {
    // 构建请求参数
    const payload = {
      keyword: nickname || username,
      pages: syncPages || 1
    };

    // 如果是日期模式，传递 before_date 参数
    if (syncMode === 'date' && syncDate) {
      payload.before_date = syncDate;
    }

    // 调搜索入库接口（强匹配关键词 = nickname）
    const res = await fetch('/api/search/author/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    // 统一返回格式给调用方
    if (data.code === 0) {
      return { success: true, added: data.data?.added || 0, message: '添加成功' };
    }
    return { success: false, message: data.msg || '添加失败' };
  } catch (e) {
    console.error('addAuthor:', e);
    return { success: false, message: e.message };
  }
}

function removeAuthor(username, nickname, authorId) {
  // 直接从本地 State 读取，不额外请求
  const authorData = _authorVideosData[username];
  const videos = authorData?.videos || {};
  const totalVideos = Object.keys(videos).length;
  const downloadedVideos = Object.values(videos).filter(v => v.downloaded).length;
  const totalSize = Object.values(videos)
    .filter(v => v.downloaded)
    .reduce((sum, v) => sum + (v.actual_size || v.size || 0), 0);

  showRemoveDialog(username, nickname, authorId, totalVideos, downloadedVideos, totalSize);
}

// 删除作者进度状态（SSE 驱动）
var _currentDeleteAuthorId = null;
var _currentDeleteUsername = null;
var _currentDeleteOverlay = null;

function showRemoveDialog(username, nickname, authorId, totalVideos, downloadedVideos, totalSize) {
  const sizeStr = totalSize > 0 ? formatFileSize(totalSize) : '0 B';
  const esc = (s) => (s || '').replace(/'/g, "\\'").replace(/"/g, '\\"');

  // 计算该作者的活跃任务数（正在下载 + 暂停中）
  const authorData = _authorVideosData[username];
  const authorVideoIds = authorData ? Object.keys(authorData.videos || {}) : [];
  const activeCount = (State.tasks.all() || []).filter(function(t) {
    return authorVideoIds.indexOf(t.video_id) >= 0 && (t.status === 'running' || t.status === 'wait' || t.status === 'pending' || t.status === 'paused');
  }).length;

  let warningHTML = '';
  if (activeCount > 0) {
    warningHTML = '<p style="margin-top:8px;padding:6px 10px;background:rgba(209,52,56,0.08);border:1px solid rgba(209,52,56,0.2);border-radius:4px;color:var(--danger);font-size:12px;">⚠ ' + activeCount + ' 个下载任务将被取消</p>';
  }

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.dataset.closable = 'true';
  overlay.innerHTML = `
    <div class="dialog-box danger">
      <div class="dialog-icon-wrapper">
        <div class="dialog-icon danger">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
          </svg>
        </div>
      </div>
      <div class="dialog-title">确认删除作者</div>
      <div class="dialog-content">
        <p>确定要删除作者 "<strong>${esc(nickname)}</strong>" 吗？</p>
        <p>视频记录: ${totalVideos} 个，已下载: ${downloadedVideos} 个 (${sizeStr})</p>
        ${warningHTML}
        <p class="dialog-hint">将同时删除作者、所有视频记录及已下载的视频文件</p>
      </div>
      <div class="dialog-buttons">
        <button class="btn-dialog secondary" onclick="closeDialog(this.closest('.dialog-overlay'))">取消</button>
        <button class="btn-dialog danger" onclick="confirmRemoveAuthor('${esc(username)}', '${esc(authorId)}', this)">删除</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}

async function confirmRemoveAuthor(username, authorId, btnEl) {
  var overlay = btnEl.closest('.dialog-overlay');
  var dialogBox = overlay.querySelector('.dialog-box');

  // 切换到进度态
  overlay.dataset.closable = 'false';
  _currentDeleteAuthorId = authorId;
  _currentDeleteUsername = username;
  _currentDeleteOverlay = overlay;

  switchDialogToProgressState(dialogBox, username);

  try {
    var res = await fetch('/api/video/author/' + encodeURIComponent(authorId) + '/all', { method: 'DELETE' });
    var data = await res.json();

    if (data.code !== 0) {
      switchDialogBackToConfirm(dialogBox, btnEl);
      overlay.dataset.closable = 'true';
      showToast({ type: 'error', title: '删除失败', message: data.msg || '未知错误' });
    }
  } catch (e) {
    switchDialogBackToConfirm(dialogBox, btnEl);
    overlay.dataset.closable = 'true';
    showToast({ type: 'error', title: '删除失败', message: e.message });
  }
}

var CIRCLE_C = 2 * Math.PI * 40;

function switchDialogToProgressState(dialogBox, username) {
  var authorData = _authorVideosData[username];
  var nickname = authorData?.nickname || username;

  // 隐藏确认态内容
  var iconWrapper = dialogBox.querySelector('.dialog-icon-wrapper');
  var content = dialogBox.querySelector('.dialog-content');
  var buttons = dialogBox.querySelector('.dialog-buttons');
  var title = dialogBox.querySelector('.dialog-title');

  if (iconWrapper) iconWrapper.style.display = 'none';
  if (content) content.style.display = 'none';
  if (buttons) buttons.style.display = 'none';
  if (title) title.style.display = 'none';
  dialogBox.classList.remove('danger');

  // 注入进度态
  var progressView = document.createElement('div');
  progressView.className = 'delete-progress-view';
  progressView.id = 'deleteProgressView';
  progressView.innerHTML =
    '<div class="delete-progress-title">正在删除 "' + nickname + '"</div>' +
    '<svg class="circle-progress-svg" viewBox="0 0 100 100" id="deleteCircleSvg">' +
      '<circle class="circle-progress-track" cx="50" cy="50" r="40" stroke-width="6" fill="none" stroke-dasharray="' + CIRCLE_C + '" stroke-dashoffset="0"/>' +
      '<circle class="circle-progress-fill" cx="50" cy="50" r="40" stroke-width="6" fill="none" stroke-dasharray="' + CIRCLE_C + '" stroke-dashoffset="' + CIRCLE_C + '" transform="rotate(-90 50 50)" id="deleteCircleFill"/>' +
      '<text class="circle-progress-text" x="50" y="50" text-anchor="middle" dominant-baseline="central" id="deleteCirclePercent">0%</text>' +
    '</svg>' +
    '<div class="delete-progress-step" id="deleteProgressStep">准备中...</div>' +
    '<div class="delete-progress-detail" id="deleteProgressDetail"></div>';
  dialogBox.appendChild(progressView);
}

function switchDialogBackToConfirm(dialogBox, btnEl) {
  var progressView = dialogBox.querySelector('#deleteProgressView');
  if (progressView) progressView.remove();

  var iconWrapper = dialogBox.querySelector('.dialog-icon-wrapper');
  var content = dialogBox.querySelector('.dialog-content');
  var buttons = dialogBox.querySelector('.dialog-buttons');
  var title = dialogBox.querySelector('.dialog-title');

  if (iconWrapper) iconWrapper.style.display = '';
  if (content) content.style.display = '';
  if (buttons) buttons.style.display = '';
  if (title) title.style.display = '';
  dialogBox.classList.add('danger');

  if (btnEl) {
    btnEl.disabled = false;
    btnEl.textContent = '删除';
  }

  _currentDeleteAuthorId = null;
  _currentDeleteOverlay = null;
  _currentDeleteUsername = null;
}

function setCircleProgress(percent) {
  var fillEl = document.getElementById('deleteCircleFill');
  var percentEl = document.getElementById('deleteCirclePercent');
  if (!fillEl || !percentEl) return;

  var offset = CIRCLE_C * (1 - Math.min(percent, 100) / 100);
  fillEl.setAttribute('stroke-dashoffset', offset);
  percentEl.textContent = Math.round(percent) + '%';
}

function handleDeleteAuthorSSEProgress(data) {
  if (data.author_id !== _currentDeleteAuthorId) return;

  var fillEl = document.getElementById('deleteCircleFill');
  var stepEl = document.getElementById('deleteProgressStep');
  var detailEl = document.getElementById('deleteProgressDetail');

  if (data.phase === 'start') {
    setCircleProgress(0);
    if (stepEl) stepEl.textContent = '正在准备删除...';
    if (detailEl) detailEl.textContent = '共 ' + (data.total_videos || 0) + ' 个视频待处理';
  } else if (data.phase === 'processing') {
    setCircleProgress(data.progress || 0);

    var stepLabels = {
      'cancel_tasks': '正在取消下载任务',
      'delete_files': '正在删除视频文件',
      'delete_dirs': '正在删除作者文件夹',
      'delete_records': '正在删除数据库记录',
    };

    if (stepEl) stepEl.textContent = stepLabels[data.step] || '正在处理...';

    if (detailEl) {
      if (data.step === 'cancel_tasks') {
        detailEl.textContent = '已取消 ' + (data.tasks_cancelled || 0) + '/' + (data.tasks_total || 0) + ' 个任务';
      } else if (data.step === 'delete_files') {
        detailEl.textContent = '已删除 ' + (data.files_deleted || 0) + '/' + (data.files_total || 0) + ' 个文件';
      } else if (data.step === 'delete_dirs') {
        detailEl.textContent = '已删除 ' + (data.dirs_deleted || 0) + '/' + (data.dirs_total || 0) + ' 个文件夹';
      } else {
        detailEl.textContent = '';
      }
    }
  } else if (data.phase === 'done') {
    if (data.error) {
      setCircleProgress(0);
      if (stepEl) stepEl.textContent = '删除失败';
      if (detailEl) detailEl.textContent = data.error;
      // 3秒后回退确认态
      setTimeout(function() {
        var dialogBox = _currentDeleteOverlay?.querySelector('.dialog-box');
        if (dialogBox) switchDialogBackToConfirm(dialogBox, null);
        if (_currentDeleteOverlay) _currentDeleteOverlay.dataset.closable = 'true';
      }, 3000);
      return;
    }

    setCircleProgress(100);
    if (fillEl) fillEl.classList.add('complete');
    if (stepEl) stepEl.textContent = '删除完成';
    if (detailEl) detailEl.textContent = '已删除 ' + (data.videos_count || 0) + ' 个视频，' + (data.files_deleted || 0) + ' 个文件';

    setTimeout(function() { switchDialogToDoneState(data); }, 500);
  }
}

function switchDialogToDoneState(data) {
  if (!_currentDeleteOverlay) return;
  var dialogBox = _currentDeleteOverlay.querySelector('.dialog-box');
  if (!dialogBox) return;

  var progressView = dialogBox.querySelector('#deleteProgressView');
  if (progressView) progressView.remove();

  var esc = (s) => (s || '').replace(/'/g, "\\'").replace(/"/g, '\\"');

  var doneView = document.createElement('div');
  doneView.className = 'delete-done-view';
  doneView.innerHTML =
    '<div class="dialog-icon-wrapper">' +
      '<div class="dialog-icon success">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
          '<path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>' +
        '</svg>' +
      '</div>' +
    '</div>' +
    '<div class="dialog-title">删除完成</div>' +
    '<div class="dialog-content">' +
      '<p>作者 "' + (decodeURIComponent(data.author_name || '')) + '" 及所有数据已删除</p>' +
      '<p class="dialog-detail">取消 ' + (data.tasks_cancelled || 0) + ' 个任务，删除 ' + (data.files_deleted || 0) + ' 个文件，' + (data.dirs_deleted || 0) + ' 个文件夹</p>' +
    '</div>' +
    '<div class="dialog-buttons">' +
      '<button class="btn-dialog primary" onclick="closeDeleteAuthorDone()">确定</button>' +
    '</div>';
  dialogBox.appendChild(doneView);

  _currentDeleteOverlay.dataset.closable = 'true';
}

function closeDeleteAuthorDone() {
  var username = _currentDeleteUsername;

  if (_currentDeleteOverlay) {
    closeDialog(_currentDeleteOverlay);
  }

  // 清理全局数据
  // 清理该作者所有任务（必须在 delete _authorVideosData 之前读取 video_ids）
  var authorVideoIds = [];
  if (_authorVideosData[username]) {
    authorVideoIds = Object.keys(_authorVideosData[username].videos || {});
  }
  authorVideoIds.forEach(function(vid) {
    State.tasks.removeByVideoId(vid);
  });
  _activeTasks = State.tasks.all();

  _allAuthors = _allAuthors.filter(a => a.username !== username);
  _catalogData = _catalogData.filter(c => c.username !== username);
  if (_authorVideosData[username]) {
    delete _authorVideosData[username];
  }

  State.authors.remove(username);
  State.catalog.remove(username);
  State.videos.removeAuthorVideos(username);

  if (typeof _prevAuthorData !== 'undefined') {
    delete _prevAuthorData[username];
  }
  if (typeof _prevCatalogData !== 'undefined') {
    delete _prevCatalogData[username];
  }

  renderAuthorGrid(_allAuthors);
  showToast({ type: 'success', title: '删除成功', message: '作者及其所有视频已删除' });

  _currentDeleteAuthorId = null;
  _currentDeleteOverlay = null;
  _currentDeleteUsername = null;
}