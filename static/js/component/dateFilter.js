// 日期筛选组件
function toggleDatePanel() {
  const panel = document.getElementById('datePanel');
  const btn = document.getElementById('dateFilterBtn');

  panel.classList.toggle('open');
  btn.classList.toggle('open');
}

document.addEventListener('click', (e) => {
  const filter = e.target.closest('.date-filter');
  if (!filter) {
    document.getElementById('datePanel')?.classList.remove('open');
    document.getElementById('dateFilterBtn')?.classList.remove('open');
  }
});

function selectDateRange(range) {
  const now = new Date();
  let start = null;
  let end = null;

  if (range === 'today') {
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
    end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
  } else if (range === '7d') {
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6, 0, 0, 0, 0);
    end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
  } else if (range === '30d') {
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29, 0, 0, 0, 0);
    end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
  } else if (range === 'month') {
    start = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0);
    end = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59, 999);
  } else if (range === 'all') {
    start = null;
    end = null;
  }

  _dateRange = { start, end };

  document.getElementById('dateFilterBtn').classList.remove('open');
  document.getElementById('datePanel').classList.remove('open');

  refreshVideoList();
}

function applyCustomDateRange() {
  const startInput = document.getElementById('dateStart');
  const endInput = document.getElementById('dateEnd');

  const startStr = startInput?.value;
  const endStr = endInput?.value;

  const start = startStr ? new Date(startStr) : null;
  const end = endStr ? new Date(endStr + 'T23:59:59') : null;

  _dateRange = { start, end };

  document.getElementById('dateFilterBtn').classList.remove('open');
  document.getElementById('datePanel').classList.remove('open');

  refreshVideoList();
}

function formatDateInput(date) {
  if (!date) return '';
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatDateDisplay(date) {
  if (!date) return '';
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function refreshVideoList() {
  if (!_currentAuthor) return;
  _currentPageNum = 1;
  if (typeof clearSelection === 'function') clearSelection();
  const filter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
  const videos = Object.values(_authorVideosData[_currentAuthor?.username || '']?.videos || {});
  renderVideoList(videos, filter);
}

function filterVideos(filter) {
  _currentPageNum = 1;
  if (typeof clearSelection === 'function') clearSelection();
  document.querySelectorAll('.video-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === filter);
  });

  // [新增] 通知 ReactiveRenderer 当前视图状态
  if (typeof ReactiveRenderer !== 'undefined') {
    ReactiveRenderer.setCurrentView(
      filter,
      _currentVideoType || 'short_video',
      _currentAuthor
    );
  }

  refreshVideoList();
}