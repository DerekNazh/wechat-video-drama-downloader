// 页面导航组件
function navigateTo(page, data = null) {
  _currentPage = page;
  State.ui.setCurrentPage(page);

  // 隐藏所有页面
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

  // 显示目标页面
  document.getElementById('page' + page.charAt(0).toUpperCase() + page.slice(1)).classList.add('active');

  // 更新返回按钮
  const btnBack = document.getElementById('btnBack');
  btnBack.style.display = page === 'home' ? 'none' : 'block';

  // 更新标题
  const titles = {
    home: '视频号<em>短视频控制台</em>',
    author: data?.name || '作者详情',
    search: '搜索作者',
    settings: '系统<em>设置</em>'
  };
  document.getElementById('pageTitle').innerHTML = titles[page] || '视频号短视频控制台';

  // 页面特定初始化
  if (page === 'author' && data) {
    loadAuthorDetail(data.username);
  }
  if (page === 'search') {
    document.getElementById('searchInput').focus();
  }
  if (page === 'settings') {
    loadSettings();
  }
}

async function goBack() {
  if (_currentPage === 'author') {
    _currentAuthor = null;
    if (typeof clearSelection === 'function') clearSelection();
    navigateTo('home');
    refreshAuthors().then(() => {
      if (_currentAuthorFilter !== 'all') {
        filterAuthors(_currentAuthorFilter);
      }
      const query = getHomeSearchQuery();
      if (query && typeof filterAuthorsWithSearch === 'function') {
        filterAuthorsWithSearch(query, { resetPage: false, updateInput: false });
      }
    });
  } else if (_currentPage === 'search' || _currentPage === 'settings') {
    navigateTo('home');
    refreshAuthors();
  }
}

function showQROverlay() {
  document.getElementById('qrOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';
}

function hideQROverlay(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('qrOverlay').classList.remove('active');
  document.body.style.overflow = '';
}