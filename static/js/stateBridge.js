// ==================== State 桥接层 ====================
// State 层为唯一数据源，全局变量从 State 同步（向后兼容）

// pollOnce 数据 → State 层 → 全局变量（单向流）
function bridgePollUpdate(data) {
  if (data.authors && data.authors.length > 0) {
    State.authors.setAll(data.authors);
    if (typeof _allAuthors !== 'undefined') _allAuthors = State.authors.all();
  }

  if (data.catalog && data.catalog.length > 0) {
    State.catalog.setAll(data.catalog);
    if (typeof _catalogData !== 'undefined') _catalogData = State.catalog.all();
  }

  if (data.author_videos && Object.keys(data.author_videos).length > 0) {
    for (var username in data.author_videos) {
      var entry = data.author_videos[username];
      var videoList = Object.values(entry.videos || {});
      var nickname = entry.nickname || username;
      State.videos.setAuthorVideos(username, videoList, nickname);
    }
    if (typeof _authorVideosData !== 'undefined') _authorVideosData = State.videos.allGrouped();
  }

  if (data.tasks) {
    State.tasks.setAll(data.tasks);
    if (typeof _activeTasks !== 'undefined') _activeTasks = State.tasks.all();
  }
}
