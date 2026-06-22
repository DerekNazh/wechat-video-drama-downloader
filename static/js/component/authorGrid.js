// 作者列表增量更新组件
let _prevAuthorData = {};
let _prevCatalogData = {};

function updateAuthorGridFromPoll() {
  // 首次加载或没有数据时全量渲染
  if (!_prevAuthorData || Object.keys(_prevAuthorData).length === 0) {
    _allAuthors.forEach(a => { _prevAuthorData[a.username] = a; });
    _catalogData.forEach(c => { _prevCatalogData[c.username] = c; });
    filterAuthors(_currentAuthorFilter);
    return;
  }

  // 如果不在作者详情页，更新作者卡片（增量）
  if (_currentPage !== 'author') {
    // 检查作者列表变化
    const newUsernames = new Set(_allAuthors.map(a => a.username));
    const oldUsernames = new Set(Object.keys(_prevAuthorData));

    // 有新增作者时重新渲染
    if (newUsernames.size !== oldUsernames.size ||
        [...newUsernames].some(u => !oldUsernames.has(u))) {
      filterAuthors(_currentAuthorFilter);
    }

    // 更新每个作者的统计（不重新渲染整个列表）
    _allAuthors.forEach(author => {
      const isListView = State.ui.getAuthorViewMode() === 'list';
      const el = isListView
        ? document.querySelector(`.author-list-item[data-username="${author.username}"]`)
        : document.querySelector(`.author-card[onclick*="${author.username}"]`);
      if (!el) return;

      // 检查是否有变化
      const oldAuthor = _prevAuthorData[author.username];
      const oldCat = _prevCatalogData[author.username];
      const newCat = _catalogData.find(c => c.username === author.username);

      // 如果数据没变化，跳过
      if (oldAuthor && oldAuthor.status === author.status &&
          oldCat && oldCat.short_video_count === newCat?.short_video_count &&
          oldCat?.short_video_downloaded === newCat?.short_video_downloaded &&
          oldCat?.replay_count === newCat?.replay_count &&
          oldCat?.replay_downloaded === newCat?.replay_downloaded) {
        return;
      }

      const cat = newCat || {};
      // 使用分类统计字段
      const shortVideoCount = cat.short_video_count || 0;
      const replayCount = cat.replay_count || 0;
      const shortVideoDownloaded = cat.short_video_downloaded || 0;
      const replayDownloaded = cat.replay_downloaded || 0;
      const total = shortVideoCount + replayCount;
      const downloaded = shortVideoDownloaded + replayDownloaded;
      const pending = cat.pending || 0;
      const progress = cat.progress || 0;

      if (isListView) {
        // 列表模式增量更新
        const nums = el.querySelectorAll('.author-list-stats .num');
        // 格式：短视频 已下载/总数 · 回放 已下载/总数
        if (nums[0]) nums[0].textContent = `${shortVideoDownloaded}/${shortVideoCount}`;
        if (nums[1]) nums[1].textContent = `${replayDownloaded}/${replayCount}`;

        const progressFill = el.querySelector('.author-list-progress-fill');
        if (progressFill) progressFill.style.width = `${progress}%`;

        const percent = el.querySelector('.author-list-percent');
        if (percent) percent.textContent = `${progress}%`;

        // 状态标签更新
        let statusClass = 'idle';
        let statusText = '空闲';
        if (author.status === 'downloading') {
          statusClass = 'downloading';
          statusText = '下载中';
        } else if (pending === 0 && total > 0) {
          statusClass = 'done';
          statusText = '已完成';
        }

        const statusEl = el.querySelector('.author-list-status');
        if (statusEl) {
          statusEl.className = `author-list-status ${statusClass}`;
          statusEl.textContent = statusText;
        }

        const statusDot = el.querySelector('.status-dot');
        if (statusDot) {
          statusDot.className = `status-dot ${statusClass}`;
        }

        // 下载中行样式
        el.classList.toggle('downloading', author.status === 'downloading');
      } else {
        // 卡片模式增量更新
        const statItems = el.querySelectorAll('.stat-item .value');
        // 格式：短视频 已下载/总数，回放 已下载/总数
        if (statItems[0]) statItems[0].textContent = `${shortVideoDownloaded}/${shortVideoCount}`;
        if (statItems[1]) statItems[1].textContent = `${replayDownloaded}/${replayCount}`;

        const progressFill = el.querySelector('.author-progress-fill');
        const progressText = el.querySelector('.author-progress-text');
        if (progressFill) progressFill.style.width = `${progress}%`;
        if (progressText) progressText.textContent = `${progress}% 完成`;
      }
    });
  }

  // 更新保存的数据
  _prevAuthorData = {};
  _allAuthors.forEach(a => { _prevAuthorData[a.username] = a; });
  _prevCatalogData = {};
  _catalogData.forEach(c => { _prevCatalogData[c.username] = c; });
}
