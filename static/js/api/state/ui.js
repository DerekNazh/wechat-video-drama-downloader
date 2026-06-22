// ==================== UI 状态 ====================

var _ui_currentAuthor = null;
var _ui_selectedVideos = new Set();
var _ui_currentPage = 'home';
var _ui_authorViewMode = localStorage.getItem('authorViewMode') || 'grid';
var _ui_videoViewMode = localStorage.getItem('videoViewMode') || 'list';
var _ui_currentAuthorFilter = 'all';
var _ui_currentPageNum = 1;
var _ui_authorPageNum = 1;
var PAGE_SIZE = 50;
var AUTHOR_PAGE_SIZE = 20;
var AUTHOR_LIST_PAGE_SIZE = 50;
var _ui_dateRange = { start: null, end: null };

// 全局别名（组件直接用这些变量名）
var _currentPageNum = 1;
var _authorPageNum = 1;
var _currentView = _ui_authorViewMode;  // 作者列表视图
var _currentVideoView = _ui_videoViewMode;  // 视频列表视图
var _dateRange = { start: null, end: null };

State.ui = {
  // 当前作者
  setCurrentAuthor: function(author) { _ui_currentAuthor = author; State.emit('ui:authorChange', author); },
  getCurrentAuthor: function() { return _ui_currentAuthor; },

  // 视频选择
  addSelectedVideo: function(videoId) { _ui_selectedVideos.add(videoId); State.emit('ui:selectionChange', { action: 'add', videoId: videoId }); },
  removeSelectedVideo: function(videoId) { _ui_selectedVideos.delete(videoId); State.emit('ui:selectionChange', { action: 'remove', videoId: videoId }); },
  clearSelectedVideos: function() { _ui_selectedVideos.clear(); State.emit('ui:selectionChange', { action: 'clear' }); },
  getSelectedVideos: function() { return _ui_selectedVideos; },
  hasSelectedVideo: function(videoId) { return _ui_selectedVideos.has(videoId); },

  // 页面导航
  setCurrentPage: function(page) { _ui_currentPage = page; State.emit('ui:pageChange', page); },
  getCurrentPage: function() { return _ui_currentPage; },

  // 作者列表视图模式
  setAuthorViewMode: function(view) { _ui_authorViewMode = view; _currentView = view; localStorage.setItem('authorViewMode', view); State.emit('ui:authorViewChange', view); },
  getAuthorViewMode: function() { return _ui_authorViewMode; },

  // 视频列表视图模式
  setVideoViewMode: function(view) { _ui_videoViewMode = view; _currentVideoView = view; localStorage.setItem('videoViewMode', view); State.emit('ui:videoViewChange', view); },
  getVideoViewMode: function() { return _ui_videoViewMode; },

  // 作者筛选
  setCurrentAuthorFilter: function(filter) { _ui_currentAuthorFilter = filter; State.emit('ui:filterChange', filter); },
  getCurrentAuthorFilter: function() { return _ui_currentAuthorFilter; },

  // 分页
  setCurrentPageNum: function(num) { _ui_currentPageNum = num; _currentPageNum = num; },
  getCurrentPageNum: function() { return _ui_currentPageNum; },
  setAuthorPageNum: function(num) { _ui_authorPageNum = num; _authorPageNum = num; },
  getAuthorPageNum: function() { return _ui_authorPageNum; },

  // 日期筛选
  setDateRange: function(start, end) { _ui_dateRange = { start: start, end: end }; _dateRange = _ui_dateRange; State.emit('ui:dateRangeChange', { start: start, end: end }); },
  getDateRange: function() { return _ui_dateRange; }
};
