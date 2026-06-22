// 分页组件
function buildPagination(totalPages, totalCount) {
  const current = _currentPageNum;
  const from = (_currentPageNum - 1) * PAGE_SIZE + 1;
  const to = Math.min(_currentPageNum * PAGE_SIZE, totalCount);

  let pages = '';
  const range = computePageRange(current, totalPages, 7);
  if (range[0] > 1) {
    pages += `<button class="page-btn" onclick="goToPage(1)">1</button>`;
    if (range[0] > 2) pages += `<span class="page-ellipsis">...</span>`;
  }
  range.forEach(p => {
    pages += `<button class="page-btn ${p === current ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
  });
  if (range[range.length - 1] < totalPages) {
    if (range[range.length - 1] < totalPages - 1) pages += `<span class="page-ellipsis">...</span>`;
    pages += `<button class="page-btn" onclick="goToPage(${totalPages})">${totalPages}</button>`;
  }

  return `
    <div class="pagination">
      <span class="page-info">${from}-${to} / ${totalCount}</span>
      <div class="page-btns">
        <button class="page-btn nav" onclick="goToPage(${current - 1})" ${current <= 1 ? 'disabled' : ''}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2L4 6L8 10"/></svg>
        </button>
        ${pages}
        <button class="page-btn nav" onclick="goToPage(${current + 1})" ${current >= totalPages ? 'disabled' : ''}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2L8 6L4 10"/></svg>
        </button>
      </div>
    </div>
  `;
}

function buildAuthorPagination(totalPages, totalCount) {
  const current = _authorPageNum;
  const from = (_authorPageNum - 1) * AUTHOR_PAGE_SIZE + 1;
  const to = Math.min(_authorPageNum * AUTHOR_PAGE_SIZE, totalCount);

  let pages = '';
  const range = computePageRange(current, totalPages, 5);
  if (range[0] > 1) {
    pages += `<button class="page-btn" onclick="goToAuthorPage(1)">1</button>`;
    if (range[0] > 2) pages += `<span class="page-ellipsis">...</span>`;
  }
  range.forEach(p => {
    pages += `<button class="page-btn ${p === current ? 'active' : ''}" onclick="goToAuthorPage(${p})">${p}</button>`;
  });
  if (range[range.length - 1] < totalPages) {
    if (range[range.length - 1] < totalPages - 1) pages += `<span class="page-ellipsis">...</span>`;
    pages += `<button class="page-btn" onclick="goToAuthorPage(${totalPages})">${totalPages}</button>`;
  }

  return `
    <div class="pagination">
      <span class="page-info">${from}-${to} / ${totalCount}</span>
      <div class="page-btns">
        <button class="page-btn nav" onclick="goToAuthorPage(${current - 1})" ${current <= 1 ? 'disabled' : ''}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2L4 6L8 10"/></svg>
        </button>
        ${pages}
        <button class="page-btn nav" onclick="goToAuthorPage(${current + 1})" ${current >= totalPages ? 'disabled' : ''}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2L8 6L4 10"/></svg>
        </button>
      </div>
    </div>
  `;
}

function goToAuthorPage(page) {
  _authorPageNum = page;
  // 翻页时不重置页码、不更新搜索框
  filterAuthorsWithSearch(getHomeSearchQuery ? getHomeSearchQuery() : '', { resetPage: false, updateInput: false });
  document.getElementById('authorGrid')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function goToPage(page) {
  _currentPageNum = page;
  const filter = document.querySelector('.video-tab.active')?.dataset.tab || 'all';
  const videos = Object.values(_authorVideosData[_currentAuthor?.username]?.videos || {});
  renderVideoList(videos, filter);
  document.getElementById('videoList')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function computePageRange(current, total, maxVisible) {
  let start = Math.max(1, current - Math.floor(maxVisible / 2));
  let end = Math.min(total, start + maxVisible - 1);
  if (end - start < maxVisible - 1) {
    start = Math.max(1, end - maxVisible + 1);
  }
  const range = [];
  for (let i = start; i <= end; i++) {
    range.push(i);
  }
  return range;
}

