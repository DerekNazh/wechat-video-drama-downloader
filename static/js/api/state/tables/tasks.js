// State.tasks — 以 video_id 为主键的任务状态表
(function() {

  var _tasks = new Map();       // key = video_id, value = task object
  var _taskIdIndex = new Map(); // key = task_id, value = video_id (反向索引)

  function _emit(event, data) {
    if (typeof State !== 'undefined' && State.emit) {
      State.emit(event, data);
    }
  }

  function _emitChanges(changes) {
    changes.forEach(function(c) {
      if (c.old) {
        _emit('tasks:update', { videoId: c.videoId, task: c.task, changes: c.old });
      } else {
        _emit('tasks:add', { videoId: c.videoId, task: c.task });
      }
    });
  }

  function setAll(list) {
    if (!Array.isArray(list)) return;
    var changes = [];
    list.forEach(function(task) {
      if (!task || !task.video_id) return;
      var key = task.video_id;
      var old = _tasks.get(key);
      var newTask;
      if (old) {
        // merge：保留 SSE 实时进度（percent/speed/downloaded/size），只同步后端字段
        newTask = {};
        for (var k in old) { if (old.hasOwnProperty(k)) newTask[k] = old[k]; }
        newTask.id = task.id;
        newTask.status = task.status;
        newTask.video_id = task.video_id;
        newTask.name = task.name || old.name;
      } else {
        newTask = task;
      }
      if (!old || old.id !== task.id) {
        newTask._taskIdChanged = true;
        newTask._oldPercent = old ? old.percent : 0;
        _taskIdIndex.set(task.id, key);
      }
      _tasks.set(key, newTask);
      changes.push({ videoId: key, task: newTask, old: old });
    });
    // 只做 upsert，不做删除
    // 删除由显式 removeByVideoId 调用完成
    _emitChanges(changes);
  }

  function get(videoId) {
    return _tasks.get(videoId) || null;
  }

  function getByTaskId(taskId) {
    var videoId = _taskIdIndex.get(taskId);
    return videoId ? _tasks.get(videoId) : null;
  }

  function update(videoId, patch) {
    var task = _tasks.get(videoId);
    if (!task) return;
    var updated = {};
    for (var k in task) { if (task.hasOwnProperty(k)) updated[k] = task[k]; }
    for (var k in patch) { if (patch.hasOwnProperty(k)) updated[k] = patch[k]; }
    // 如果 task_id 变了，更新反向索引
    if (patch.id && patch.id !== task.id) {
      _taskIdIndex.delete(task.id);
      _taskIdIndex.set(patch.id, videoId);
      updated._taskIdChanged = true;
    }
    _tasks.set(videoId, updated);
    _emit('tasks:update', { videoId: videoId, task: updated, changes: patch });
  }

  function removeByVideoId(videoId) {
    var task = _tasks.get(videoId);
    if (task && task.id) {
      _taskIdIndex.delete(task.id);
    }
    _tasks.delete(videoId);
  }

  function removeByTaskId(taskId) {
    var videoId = _taskIdIndex.get(taskId);
    if (videoId) {
      removeByVideoId(videoId);
    }
  }

  function all() {
    return Array.from(_tasks.values());
  }

  function clear() {
    _tasks.clear();
    _taskIdIndex.clear();
  }

  function getByVideoId(videoId) {
    // 别名，兼容旧调用
    return get(videoId);
  }

  // 暴露公共接口
  window.State = window.State || {};
  window.State.tasks = {
    setAll: setAll,
    get: get,
    getByTaskId: getByTaskId,
    getByVideoId: getByVideoId,
    update: update,
    removeByVideoId: removeByVideoId,
    removeByTaskId: removeByTaskId,
    all: all,
    clear: clear
  };

})();
