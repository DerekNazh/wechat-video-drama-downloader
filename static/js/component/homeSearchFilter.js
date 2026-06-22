// 首页搜索过滤组件
// 搜索框输入后直接过滤作者列表（无下拉面板）
// 过滤后重置分页到第一页

// 依赖: _allAuthors (全局变量，在 app.js 中定义)
// 依赖: filterAuthorsWithSearch (函数，在 authorGridRender.js 中定义)
// 依赖: _homeSearchQuery (全局变量，存储当前搜索词)

// ============================================================
// 常量
// ============================================================

const HOME_SEARCH_DEBOUNCE_MS = 300;

// ============================================================
// 状态
// ============================================================

let _homeSearchDebounceTimer = null;
let _homeSearchQuery = '';  // 当前搜索词

// ============================================================
// 公开接口
// ============================================================

/**
 * 获取当前搜索词
 */
function getHomeSearchQuery() {
  return _homeSearchQuery;
}

/**
 * 判断是否有搜索词
 */
function hasHomeSearchQuery() {
  return _homeSearchQuery && _homeSearchQuery.trim().length > 0;
}

// ============================================================
// 事件处理
// ============================================================

/**
 * 处理输入事件（带防抖）
 */
function homeSearchHandleInput() {
  const input = document.getElementById('homeSearchInput');
  if (!input) return;

  const query = input.value;

  // 清除之前的定时器
  if (_homeSearchDebounceTimer) {
    clearTimeout(_homeSearchDebounceTimer);
    _homeSearchDebounceTimer = null;
  }

  // 空查询直接清空搜索
  if (!query.trim()) {
    _homeSearchQuery = '';
    // 重新渲染完整列表
    if (typeof filterAuthorsWithSearch === 'function') {
      filterAuthorsWithSearch('');
    }
    return;
  }

  // 防抖过滤
  _homeSearchDebounceTimer = setTimeout(() => {
    _homeSearchQuery = query;
    // 调用 authorGridRender 的过滤函数
    if (typeof filterAuthorsWithSearch === 'function') {
      filterAuthorsWithSearch(query);
    }
    _homeSearchDebounceTimer = null;
  }, HOME_SEARCH_DEBOUNCE_MS);
}

/**
 * 处理键盘事件
 * @param {KeyboardEvent} e
 */
function homeSearchHandleKeydown(e) {
  if (e.key === 'Escape') {
    homeSearchClearInput();
  }
}

/**
 * 清空搜索输入
 */
function homeSearchClearInput() {
  const input = document.getElementById('homeSearchInput');
  if (input) {
    input.value = '';
  }
  _homeSearchQuery = '';
  // 恢复完整列表
  if (typeof filterAuthorsWithSearch === 'function') {
    filterAuthorsWithSearch('');
  }
}

// ============================================================
// 初始化
// ============================================================

/**
 * 初始化首页搜索过滤组件
 */
function initHomeSearchFilter() {
  const input = document.getElementById('homeSearchInput');

  if (!input) {
    console.warn('[homeSearchFilter] 元素未找到，跳过初始化');
    return;
  }

  // 输入事件
  input.addEventListener('input', homeSearchHandleInput);
  input.addEventListener('keydown', homeSearchHandleKeydown);
}

/**
 * 销毁组件（清理事件监听）
 */
function destroyHomeSearchFilter() {
  const input = document.getElementById('homeSearchInput');

  if (input) {
    input.removeEventListener('input', homeSearchHandleInput);
    input.removeEventListener('keydown', homeSearchHandleKeydown);
  }

  if (_homeSearchDebounceTimer) {
    clearTimeout(_homeSearchDebounceTimer);
    _homeSearchDebounceTimer = null;
  }

  _homeSearchQuery = '';
}

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', initHomeSearchFilter);
