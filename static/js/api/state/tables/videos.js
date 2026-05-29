// ==================== 视频表 ====================

var _videos = new Map(); // username -> Map(video_id -> Video)

var _authorMeta = new Map(); // username -> { username, nickname }

// 反向索引：video_id -> username（快速查找视频所属作者）
var _videoToAuthor = new Map();

function _detectVideoChanges(oldRecord, newRecord) {
  if (!oldRecord) return { action: 'add', data: newRecord };

  var changes = {};
  var hasChange = false;

  for (var key in newRecord) {
    if (oldRecord[key] !== newRecord[key]) {
      changes[key] = { old: oldRecord[key], new: newRecord[key] };
      hasChange = true;
    }
  }

  if (!hasChange) return null;
  return { action: 'update', id: newRecord.id, changes: changes };
}

State.videos = {
  // 设置单个作者的视频列表
  setAuthorVideos: function(username, list, nickname) {
    var videoMap = new Map();
    list.forEach(function(video) {
      videoMap.set(video.id, video);
      // 维护反向索引
      _videoToAuthor.set(video.id, username);
    });

    var oldMap = _videos.get(username) || new Map();

    var added = [];
    var deleted = [];
    var updated = [];

    videoMap.forEach(function(video, id) {
      if (!oldMap.has(id)) {
        added.push(video);
      } else {
        var change = _detectVideoChanges(oldMap.get(id), video);
        if (change) updated.push(change);
      }
    });

    oldMap.forEach(function(_, id) {
      if (!videoMap.has(id)) {
        deleted.push(id);
        // 清理反向索引
        _videoToAuthor.delete(id);
      }
    });

    _videos.set(username, videoMap);
    _authorMeta.set(username, { username: username, nickname: nickname || username });

    if (added.length) State.emit('videos:add', { username: username, list: added });
    if (deleted.length) State.emit('videos:delete', { username: username, ids: deleted });
    if (updated.length) State.emit('videos:update', { username: username, changes: updated });
    State.emit('videos:loaded', { username: username, count: list.length });
  },

  // 从 _authorVideosData 嵌套结构批量导入
  setAllFromAuthorVideos: function(authorVideosData) {
    for (var username in authorVideosData) {
      var entry = authorVideosData[username];
      var videos = entry.videos || {};
      var list = Object.values(videos);
      State.videos.setAuthorVideos(username, list);
    }
  },

  update: function(username, video) {
    var authorVideos = _videos.get(username) || new Map();
    var old = authorVideos.get(video.id);
    var change = _detectVideoChanges(old, video);
    if (!change) return;
    authorVideos.set(video.id, video);
    _videos.set(username, authorVideos);
    State.emit('videos:update', { username: username, changes: [change] });
  },

  removeAuthorVideos: function(username) {
    if (!_videos.has(username)) return;
    _videos.delete(username);
    _authorMeta.delete(username);
    State.emit('videos:delete', { username: username, ids: [] });
  },

  get: function(username, videoId) {
    var authorVideos = _videos.get(username);
    return authorVideos ? authorVideos.get(videoId) : null;
  },

  getAuthorVideos: function(username) {
    var authorVideos = _videos.get(username);
    return authorVideos ? Array.from(authorVideos.values()) : [];
  },

  all: function() {
    var result = [];
    _videos.forEach(function(videos) {
      result = result.concat(Array.from(videos.values()));
    });
    return result;
  },

  allGrouped: function() {
    var result = {};
    _videos.forEach(function(videoMap, username) {
      var meta = _authorMeta.get(username) || { username: username, nickname: username };
      result[username] = {
        username: meta.username,
        nickname: meta.nickname,
        videos: {}
      };
      videoMap.forEach(function(v, vid) {
        result[username].videos[vid] = v;
      });
    });
    return result;
  },

  find: function(filter) {
    return State.videos.all().filter(filter);
  },

  size: function() {
    return _videos.size;
  },

  // ==================== 新增：响应式状态管理 ====================

  // 更新单个视频状态（触发 videos:status 事件）
  updateStatus: function(videoId, updates) {
    var username = _videoToAuthor.get(videoId);
    if (!username) {
      console.warn('[State.videos] updateStatus: 视频不存在', videoId);
      return;
    }

    var authorVideos = _videos.get(username);
    if (!authorVideos) return;

    var video = authorVideos.get(videoId);
    if (!video) return;

    var oldDownloaded = video.downloaded;
    var oldType = video.video_type || 'short_video';

    // 应用更新
    for (var key in updates) {
      video[key] = updates[key];
    }

    var newDownloaded = video.downloaded;
    var newType = video.video_type || 'short_video';

    // 触发事件
    State.emit('videos:status', {
      videoId: videoId,
      username: username,
      video: video,
      changes: {
        downloaded: { old: oldDownloaded, new: newDownloaded },
        video_type: { old: oldType, new: newType }
      }
    });
  },

  // 按类型获取统计（实时计算）
  getStatsByType: function(username) {
    var videos = this.getAuthorVideos(username);
    var shortVideoTotal = 0, shortVideoDownloaded = 0;
    var replayTotal = 0, replayDownloaded = 0;

    videos.forEach(function(v) {
      var type = v.video_type || 'short_video';
      if (type === 'short_video') {
        shortVideoTotal++;
        if (v.downloaded) shortVideoDownloaded++;
      } else if (type === 'live_replay') {
        replayTotal++;
        if (v.downloaded) replayDownloaded++;
      }
    });

    return {
      short_video: { total: shortVideoTotal, downloaded: shortVideoDownloaded },
      live_replay: { total: replayTotal, downloaded: replayDownloaded },
      total: shortVideoTotal + replayTotal,
      downloaded: shortVideoDownloaded + replayDownloaded
    };
  },

  // 查找视频所属作者
  getAuthorByVideoId: function(videoId) {
    return _videoToAuthor.get(videoId) || null;
  }
};
