// 历史面板组件
var _historyTabActive = false;

function _escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function switchDrawerTab(tab) {
  var statusContent = document.getElementById('drawerStatusContent');
  var historyContent = document.getElementById('drawerHistoryContent');
  var tabStatus = document.getElementById('drawerTabStatus');
  var tabHistory = document.getElementById('drawerTabHistory');
  var drawerBody = document.getElementById('drawerBody');

  if (!statusContent || !historyContent) return;

  if (tab === 'history') {
    _historyTabActive = true;
    statusContent.style.display = 'none';
    historyContent.style.display = 'block';
    if (tabStatus) tabStatus.classList.remove('active');
    if (tabHistory) tabHistory.classList.add('active');
    if (drawerBody) drawerBody.classList.add('history-active');
    // 切换到历史时刷新
    if (typeof fetchCompletionLog === 'function') {
      fetchCompletionLog(8);
    }
  } else {
    _historyTabActive = false;
    statusContent.style.display = 'block';
    historyContent.style.display = 'none';
    if (tabStatus) tabStatus.classList.add('active');
    if (tabHistory) tabHistory.classList.remove('active');
    if (drawerBody) drawerBody.classList.remove('history-active');
  }
}

function renderHistoryList() {
  var container = document.getElementById('historyList');
  if (!container) return;

  var items = (State.logs && State.logs.all()) || [];

  if (items.length === 0) {
    container.innerHTML = '<div class="history-empty">暂无下载记录</div>';
    return;
  }

  container.innerHTML = items.map(function(item) {
    var authorName = _escapeHtml(item.author_name) || '未知作者';
    var title = _escapeHtml(item.title) || '';
    var time = (typeof formatRelativeTime === 'function') ? formatRelativeTime(item.completed_at) : '';
    var size = (typeof formatFileSize === 'function') ? formatFileSize(item.file_size) : '';
    var coverUrl = item.cover_url || '';
    var username = item.username || '';
    var clickHandler = username
      ? 'loadAuthorDetail(\'' + username.replace(/'/g, "\\'") + '\')'
      : 'showToast({type:\'warning\',title:\'提示\',message:\'作者已移除\'})';

    return '<div class="history-item" onclick="' + clickHandler + '">' +
      '<img class="history-cover" src="' + coverUrl + '" alt="' + title + '" onerror="this.style.display=\'none\'">' +
      '<div class="history-info">' +
        '<div class="history-title">' + title + '</div>' +
        '<div class="history-meta">' +
          '<span class="history-author">' + authorName + '</span>' +
          '<span class="history-sep">&middot;</span>' +
          '<span class="history-time">' + time + '</span>' +
          '<span class="history-sep">&middot;</span>' +
          '<span class="history-size">' + size + '</span>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');
}
