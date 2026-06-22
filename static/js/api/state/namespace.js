// ==================== State 命名空间 + 事件总线 ====================
window.State = window.State || {};

// 事件系统
State._events = {};

State.on = function(event, callback) {
  if (!State._events[event]) State._events[event] = [];
  State._events[event].push(callback);
  return function() { State.off(event, callback); };
};

State.off = function(event, callback) {
  if (!State._events[event]) return;
  State._events[event] = State._events[event].filter(function(cb) { return cb !== callback; });
};

State.emit = function(event, data) {
  if (!State._events[event]) return;
  State._events[event].forEach(function(cb) {
    try { cb(data); } catch (e) { console.error('State.emit error:', event, e); }
  });
};
