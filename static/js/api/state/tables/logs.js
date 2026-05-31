// ==================== 任务完成记录表 ====================
// 存储任务完成日志（items 数组 + total 总数）

var _logs = [];
var _total = 0;

State.logs = {
  all: function() {
    return _logs;
  },

  getTotal: function() {
    return _total;
  },

  setLogs: function(data) {
    _logs = data.items || [];
    _total = data.total || 0;
    if (typeof State !== 'undefined' && State.emit) {
      State.emit('logs:updated', { items: _logs, total: _total });
    }
  },

  clear: function() {
    _logs = [];
    _total = 0;
    if (typeof State !== 'undefined' && State.emit) {
      State.emit('logs:cleared');
    }
  }
};
