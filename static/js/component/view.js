// 视图切换组件

function switchView(view) {
  State.ui.setVideoViewMode(view);

  document.querySelectorAll('.view-switcher .view-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });

  const list = document.getElementById('videoList');
  if (list) {
    list.style.opacity = '0';
    setTimeout(() => {
      list.classList.remove('grid-view', 'compact-view');
      if (view !== 'list') {
        list.classList.add(view + '-view');
      }
      list.style.opacity = '1';
    }, 120);
  }
}

// 初始化视频视图模式（从 localStorage 恢复）
function initVideoViewMode() {
  var savedView = localStorage.getItem('videoViewMode') || 'list';
  var view = savedView;

  // 更新按钮状态
  document.querySelectorAll('.view-switcher .view-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });

  // 应用视图样式
  const list = document.getElementById('videoList');
  if (list && view !== 'list') {
    list.classList.add(view + '-view');
  }
}

document.addEventListener('DOMContentLoaded', initVideoViewMode);