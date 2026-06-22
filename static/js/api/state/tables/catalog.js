// ==================== 目录统计表 ====================
// 存储作者统计信息（总数、已下载、待下载、进度）

var _catalog = new Map(); // username -> {username, total, downloaded, pending, progress}

State.catalog = {
  setAll: function(list) {
    var oldKeys = new Set(_catalog.keys());
    var newKeys = new Set(list.map(function(c) { return c.username; }));
    var added = [];
    var updated = [];

    list.forEach(function(entry) {
      if (!oldKeys.has(entry.username)) {
        added.push(entry);
      } else {
        var old = _catalog.get(entry.username);
        if (old.total !== entry.total ||
            old.downloaded !== entry.downloaded ||
            old.pending !== entry.pending ||
            old.progress !== entry.progress ||
            old.short_video_count !== entry.short_video_count ||
            old.replay_count !== entry.replay_count ||
            old.short_video_downloaded !== entry.short_video_downloaded ||
            old.replay_downloaded !== entry.replay_downloaded) {
          updated.push({ username: entry.username, old: old, new: entry });
        }
      }
      _catalog.set(entry.username, entry);
    });

    // 移除不存在的
    oldKeys.forEach(function(key) {
      if (!newKeys.has(key)) _catalog.delete(key);
    });

    if (added.length) State.emit('catalog:add', { entries: added });
    if (updated.length) State.emit('catalog:update', { changes: updated });
  },

  get: function(username) {
    return _catalog.get(username) || null;
  },

  all: function() {
    return Array.from(_catalog.values());
  },

  remove: function(username) {
    if (!_catalog.has(username)) return;
    _catalog.delete(username);
    State.emit('catalog:delete', { username: username });
  },

  size: function() {
    return _catalog.size;
  }
};
