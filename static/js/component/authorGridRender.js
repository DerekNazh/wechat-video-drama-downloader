// 作者列表渲染组件

// 当前筛选状态
let _currentAuthorFilter = 'all';

/**
 * 按搜索关键词过滤作者
 * @param {Array} authors - 作者数组
 * @param {string} query - 搜索关键词
 * @returns {Array} 过滤后的作者数组
 */
function filterAuthorsByQuery(authors, query) {
  if (!query || !query.trim()) return authors;
  const q = query.trim().toLowerCase();
  return authors.filter(a =>
    (a.nickname || '').toLowerCase().includes(q) ||
    (a.username || '').toLowerCase().includes(q)
  );
}

/**
 * 组合过滤：搜索关键词 + 状态过滤
 * @param {string} query - 搜索关键词
 * @param {Object} options - 可选配置
 * @param {boolean} options.resetPage - 是否重置分页到第一页（默认 true）
 * @param {boolean} options.updateInput - 是否更新搜索框显示（默认 true）
 */
function filterAuthorsWithSearch(query, options = {}) {
  const { resetPage = true, updateInput = true } = options;

  // 搜索时重置分页，翻页时不重置
  if (resetPage) {
    _authorPageNum = 1;
  }

  // 搜索时更新搜索框，翻页时不更新
  if (updateInput) {
    const input = document.getElementById('homeSearchInput');
    if (input && query !== undefined) {
      input.value = query;
    }
  }

  // 获取当前状态过滤
  const filter = _currentAuthorFilter;

  // 更新过滤标签状态
  document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.filter === filter);
  });

  // 构建 catalog 映射
  const catMap = {};
  _catalogData.forEach(c => { catMap[c.username] = c; });

  // 1. 先按搜索关键词过滤
  let filtered = filterAuthorsByQuery(_allAuthors, query);

  // 2. 再按状态过滤
  if (filter === 'downloading') {
    filtered = filtered.filter(a => a.status === 'downloading');
  } else if (filter === 'idle') {
    filtered = filtered.filter(a => {
      const cat = catMap[a.username] || {};
      const pending = cat.pending || 0;
      return a.status !== 'downloading' && pending > 0;
    });
  }

  renderAuthorGrid(filtered);
}

function renderAuthorGrid(list) {
  const el = document.getElementById("authorGrid");

  // 移除旧的列表容器类
  el.classList.remove('author-list');

  if (list.length === 0) {
    el.innerHTML = `
      <div class="author-empty">
        <div class="empty-icon">o</div>
        <p>暂无监控作者</p>
        <span>点击上方搜索框添加作者</span>
      </div>
    `;
    return;
  }

  // 更新视图切换按钮状态
  updateViewToggle();

  // 根据视图模式渲染
  if (_currentView === 'list') {
    renderAuthorListView(el, list);
  } else {
    renderAuthorCardView(el, list);
  }
}

function renderAuthorListView(el, list) {
  el.classList.add('author-list');

  const pageSize = typeof AUTHOR_LIST_PAGE_SIZE !== 'undefined' ? AUTHOR_LIST_PAGE_SIZE : 50;
  const totalPages = Math.ceil(list.length / pageSize);
  if (_authorPageNum > totalPages) _authorPageNum = totalPages;
  if (_authorPageNum < 1) _authorPageNum = 1;
  const startIdx = (_authorPageNum - 1) * pageSize;
  const pageAuthors = list.slice(startIdx, startIdx + pageSize);

  const catMap = {};
  _catalogData.forEach(c => { catMap[c.username] = c; });

  let html = '';
  pageAuthors.forEach(author => {
    const cat = catMap[author.username] || {};
    // 使用分类统计：短视频数/回放数/已下载
    const shortVideoCount = cat.short_video_count || 0;
    const replayCount = cat.replay_count || 0;
    const shortVideoDownloaded = cat.short_video_downloaded || 0;
    const replayDownloaded = cat.replay_downloaded || 0;
    const downloaded = shortVideoDownloaded + replayDownloaded;
    const total = shortVideoCount + replayCount;
    const pending = cat.pending || 0;
    const progress = cat.progress || 0;

    let statusClass = 'idle';
    let statusText = '空闲';
    if (author.status === 'downloading') {
      statusClass = 'downloading';
      statusText = '下载中';
    } else if (pending === 0 && total > 0) {
      statusClass = 'done';
      statusText = '已完成';
    }

    const initial = (author.nickname || '?')[0];
    const avatarHtml = author.head_url
      ? `<img src="${author.head_url}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><span class="fallback" style="display:none">${initial}</span>`
      : `<span class="fallback">${initial}</span>`;

    const escNickname = (author.nickname || '').replace(/'/g, "\\'");

    html += `
      <div class="author-list-item ${author.status === 'downloading' ? 'downloading' : ''}"
           data-username="${author.username}"
           onclick="openAuthorDetail('${author.username}', '${escNickname}')">
        <div class="author-list-avatar">
          ${avatarHtml}
          <span class="status-dot ${statusClass}"></span>
        </div>
        <div class="author-list-name">${author.nickname || '未知'}</div>
        <span class="author-list-status ${statusClass}">${statusText}</span>
        <div class="author-list-stats">
          <span class="num short-video">${shortVideoDownloaded}/${shortVideoCount}</span><span class="sep">·</span>
          <span class="num replay">${replayDownloaded}/${replayCount}</span>
        </div>
        <div class="author-list-progress">
          <div class="author-list-progress-fill" style="width:${progress}%"></div>
        </div>
        <div class="author-list-percent">${progress}%</div>
        <button class="author-list-delete" onclick="event.stopPropagation(); removeAuthor('${author.username}', '${escNickname}', '${author.id}')" title="移除作者">×</button>
      </div>
    `;
  });

  if (totalPages > 1) {
    html += buildAuthorPagination(totalPages, list.length);
  }

  el.innerHTML = html;
}

function renderAuthorCardView(el, list) {
  // 原有网格卡片渲染
  const totalPages = Math.ceil(list.length / AUTHOR_PAGE_SIZE);
  if (_authorPageNum > totalPages) _authorPageNum = totalPages;
  if (_authorPageNum < 1) _authorPageNum = 1;
  const startIdx = (_authorPageNum - 1) * AUTHOR_PAGE_SIZE;
  const pageAuthors = list.slice(startIdx, startIdx + AUTHOR_PAGE_SIZE);

  const catMap = {};
  _catalogData.forEach(c => { catMap[c.username] = c; });

  let html = '';
  pageAuthors.forEach(author => {
    const cat = catMap[author.username] || {};
    // 使用分类统计：短视频数/回放数/已下载
    const shortVideoCount = cat.short_video_count || 0;
    const replayCount = cat.replay_count || 0;
    const shortVideoDownloaded = cat.short_video_downloaded || 0;
    const replayDownloaded = cat.replay_downloaded || 0;
    const downloaded = shortVideoDownloaded + replayDownloaded;
    const total = shortVideoCount + replayCount;
    const pending = cat.pending || 0;
    const progress = cat.progress || 0;

    let statusClass = 'idle';
    let statusText = '空闲';
    if (author.status === "downloading") {
      statusClass = 'downloading';
      statusText = '下载中';
    } else if (pending === 0 && total > 0) {
      statusClass = 'done';
      statusText = '已完成';
    }

    const initial = (author.nickname || '?')[0];
    const avatarHtml = author.head_url
      ? `<img src="${author.head_url}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><span class="fallback" style="display:none">${initial}</span>`
      : `<span class="fallback">${initial}</span>`;

    const escNickname = (author.nickname || '').replace(/'/g, "\\'");

    html += `
      <div class="author-card ${author.status === 'downloading' ? 'downloading' : ''}"
           data-username="${author.username}"
           onclick="openAuthorDetail('${author.username}', '${escNickname}')">
        <button class="author-delete-btn" onclick="event.stopPropagation(); removeAuthor('${author.username}', '${escNickname}', '${author.id}')" title="移除作者">×</button>
        <div class="author-card-header">
          <div class="author-avatar">${avatarHtml}</div>
          <div class="author-card-info">
            <div class="author-name">${author.nickname || '未知'}</div>
            <span class="author-status ${statusClass}">
              <span class="dot ${statusClass === 'downloading' ? 'green' : ''}"></span>
              ${statusText}
            </span>
          </div>
        </div>
        <div class="author-stats">
          <div class="stat-item short-video">
            <div class="value">${shortVideoDownloaded}/${shortVideoCount}</div>
            <div class="label">短视频</div>
          </div>
          <div class="stat-item replay">
            <div class="value">${replayDownloaded}/${replayCount}</div>
            <div class="label">直播回放</div>
          </div>
        </div>
        ${total > 0 ? `
          <div class="author-progress">
            <div class="author-progress-fill" style="width:${progress}%"></div>
          </div>
          <div class="author-progress-text">${progress}% 完成</div>
        ` : ''}
      </div>
    `;
  });

  if (totalPages > 1) {
    html += buildAuthorPagination(totalPages, list.length);
  }

  el.innerHTML = html;
}

function switchAuthorView(mode) {
  State.ui.setCurrentView(mode);
  _authorPageNum = 1;
  filterAuthors(_currentAuthorFilter);
}

function updateViewToggle() {
  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === _currentView);
  });
}

/**
 * 按状态过滤（保持搜索词）
 */
function filterAuthors(filter) {
  _currentAuthorFilter = filter;
  // 调用组合过滤，保持当前搜索词
  filterAuthorsWithSearch(getHomeSearchQuery ? getHomeSearchQuery() : '');
}

function openAuthorDetail(username, nickname) {
  // 从 _allAuthors 获取完整的作者信息（包括 id）
  const author = _allAuthors.find(a => a.username === username);
  _currentAuthor = author ? { ...author, username, nickname } : { username, nickname };
  console.log(`[openAuthorDetail] _currentAuthor=`, _currentAuthor);
  State.ui.setCurrentAuthor(_currentAuthor);
  document.querySelectorAll('.video-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === 'all');
  });
  navigateTo('author', { username, name: nickname });
}
