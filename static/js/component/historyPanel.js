// 审计记录面板组件
var _historyTabActive = false;
var _auditFilterKeyword = '';
var _auditFilterAuthor = '';  // 作者筛选（username）

function _escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _formatAuditTime(isoStr) {
  if (!isoStr) return '--';
  try {
    var d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    var mon = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    var h = String(d.getHours()).padStart(2, '0');
    var m = String(d.getMinutes()).padStart(2, '0');
    return mon + '/' + day + ' ' + h + ':' + m;
  } catch (e) {
    return isoStr;
  }
}

function _formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '--';
  var s = Math.round(seconds);
  if (s < 60) return s + 's';
  var min = Math.floor(s / 60);
  var sec = s % 60;
  if (min < 60) return min + ':' + String(sec).padStart(2, '0');
  var hr = Math.floor(min / 60);
  min = min % 60;
  return hr + ':' + String(min).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
}

function _formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return '--';
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'K';
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + 'M';
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + 'G';
}

function switchDrawerTab(tab) {
  var statusContent = document.getElementById('drawerStatusContent');
  var historyContent = document.getElementById('drawerHistoryContent');
  var tabStatus = document.getElementById('drawerTabStatus');
  var tabHistory = document.getElementById('drawerTabHistory');

  if (!statusContent || !historyContent) return;

  if (tab === 'history') {
    _historyTabActive = true;
    statusContent.style.display = 'none';
    historyContent.style.display = 'flex';
    if (tabStatus) tabStatus.classList.remove('active');
    if (tabHistory) tabHistory.classList.add('active');
    if (typeof fetchCompletionLog === 'function') {
      fetchCompletionLog(50);
    }
    // 刷新作者下拉列表（_allAuthors 可能已更新）
    if (typeof _populateAuthorSelect === 'function') {
      _populateAuthorSelect();
    }
  } else {
    _historyTabActive = false;
    statusContent.style.display = 'block';
    historyContent.style.display = 'none';
    if (tabStatus) tabStatus.classList.add('active');
    if (tabHistory) tabHistory.classList.remove('active');
  }
}

function renderHistoryList() {
  var tbody = document.getElementById('auditTableBody');
  if (!tbody) return;

  var countEl = document.getElementById('auditTotalCount');
  var items = (State.logs && State.logs.all()) || [];
  var total = (State.logs && State.logs.getTotal()) || 0;

  // 作者筛选
  if (_auditFilterAuthor) {
    items = items.filter(function(item) {
      return (item.username || '') === _auditFilterAuthor;
    });
  }

  // 关键词过滤 — 搜索所有字段
  var keyword = _auditFilterKeyword.toLowerCase().trim();
  if (keyword) {
    items = items.filter(function(item) {
      var fields = [
        item.title || '',
        item.author_name || '',
        item.username || '',
        item.video_id || '',
        item.author_id || '',
        _formatAuditTime(item.completed_at),
        _formatFileSize(item.file_size),
        _formatDuration(item.duration),
      ];
      return fields.some(function(f) { return f.toLowerCase().indexOf(keyword) !== -1; });
    });
  }

  if (countEl) {
    if (keyword || _auditFilterAuthor) {
      countEl.textContent = items.length + '/' + total + ' 条';
    } else {
      countEl.textContent = total + ' 条';
    }
  }

  if (items.length === 0) {
    var emptyMsg = (keyword || _auditFilterAuthor) ? '无匹配记录' : '暂无下载记录';
    tbody.innerHTML = '<tr><td colspan="5" class="audit-empty">' + emptyMsg + '</td></tr>';
    return;
  }

  var html = '';
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var authorName = _escapeHtml(item.author_name) || '--';
    var title = _escapeHtml(item.title) || '--';
    var time = _formatAuditTime(item.completed_at);
    var size = _formatFileSize(item.file_size);
    var duration = _formatDuration(item.duration);
    var username = item.username || '';
    var clickHandler = username
      ? 'loadAuthorDetail(\'' + username.replace(/'/g, "\\'") + '\')'
      : '';

    html += '<tr' + (clickHandler ? ' onclick="' + clickHandler + '"' : '') + '>' +
      '<td class="col-time">' + time + '</td>' +
      '<td class="col-author">' + authorName + '</td>' +
      '<td class="col-title" title="' + _escapeHtml(item.title || '') + '">' + title + '</td>' +
      '<td class="col-size">' + size + '</td>' +
      '<td class="col-duration">' + duration + '</td>' +
    '</tr>';
  }
  tbody.innerHTML = html;
}

// 从全局作者列表中提取不重复的作者，用于下拉筛选
// 使用 _allAuthors（全量）而非日志（分页），确保下拉列表完整
function _getAuthorOptions() {
  var authors = (typeof _allAuthors !== 'undefined' && _allAuthors) || [];
  var result = [];
  for (var i = 0; i < authors.length; i++) {
    var a = authors[i];
    var username = a.username || '';
    var name = a.nickname || a.name || username;
    if (!username) continue;
    result.push({ username: username, name: name });
  }
  result.sort(function(a, b) { return a.name.localeCompare(b.name, 'zh'); });
  return result;
}

// 初始化过滤输入框事件
(function initAuditFilter() {
  var filterInput = document.getElementById('auditFilterInput');
  if (filterInput) {
    var _filterTimer = null;

    filterInput.addEventListener('input', function(e) {
      var val = e.target.value;
      // 防抖 200ms
      if (_filterTimer) clearTimeout(_filterTimer);
      _filterTimer = setTimeout(function() {
        _auditFilterKeyword = val;
        renderHistoryList();
      }, 200);
    });

    // ESC 清空过滤
    filterInput.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        filterInput.value = '';
        _auditFilterKeyword = '';
        renderHistoryList();
        e.stopPropagation();
      }
    });
  }

  // 作者下拉筛选
  var authorSelect = document.getElementById('auditAuthorSelect');
  if (authorSelect) {
    authorSelect.addEventListener('change', function(e) {
      _auditFilterAuthor = e.target.value;
      renderHistoryList();
    });
  }

  // 数据更新时刷新作者下拉选项
  if (typeof State !== 'undefined' && State.on) {
    State.on('logs:updated', function() {
      _populateAuthorSelect();
    });
  }
})();

function _populateAuthorSelect() {
  var authorSelect = document.getElementById('auditAuthorSelect');
  if (!authorSelect) return;

  var authors = _getAuthorOptions();
  var currentVal = _auditFilterAuthor;

  var html = '<option value="">全部作者</option>';
  for (var i = 0; i < authors.length; i++) {
    var a = authors[i];
    var selected = a.username === currentVal ? ' selected' : '';
    html += '<option value="' + _escapeHtml(a.username) + '"' + selected + '>' + _escapeHtml(a.name) + '</option>';
  }
  authorSelect.innerHTML = html;
}
