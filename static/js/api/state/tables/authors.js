// ==================== 作者表 ====================

var _authors = new Map(); // username -> Author

function _detectAuthorChanges(oldRecord, newRecord) {
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
  return { action: 'update', id: newRecord.username || newRecord.id, changes: changes };
}

State.authors = {
  setAll: function(list) {
    var added = [];
    var updated = [];

    var newKeys = new Set(list.map(function(a) { return a.username; }));

    list.forEach(function(author) {
      var key = author.username;
      var old = _authors.get(key);
      var change = _detectAuthorChanges(old, author);

      if (!old) {
        added.push(author);
      } else if (change) {
        updated.push(change);
      }

      _authors.set(key, author);
    });

    // 移除不存在的
    _authors.forEach(function(_, key) {
      if (!newKeys.has(key)) _authors.delete(key);
    });

    if (added.length) State.emit('authors:add', { authors: added });
    if (updated.length) State.emit('authors:update', { changes: updated });
  },

  update: function(author) {
    var old = _authors.get(author.username);
    var change = _detectAuthorChanges(old, author);
    if (!change) return;
    _authors.set(author.username, author);
    State.emit('authors:update', { changes: [change] });
  },

  remove: function(username) {
    if (!_authors.has(username)) return;
    _authors.delete(username);
    State.emit('authors:delete', { username: username });
  },

  get: function(username) {
    return _authors.get(username) || null;
  },

  all: function() {
    return Array.from(_authors.values());
  },

  find: function(filter) {
    return State.authors.all().filter(filter);
  },

  size: function() {
    return _authors.size;
  }
};
