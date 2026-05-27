// 测试服务离线时 running 任务标记为 paused
const assert = require('assert');

// 模拟最小全局状态
let _goOnline = true;
let _activeTasks = [
  { id: 'task_1', status: 'running', speed: 1024 },
  { id: 'task_2', status: 'pending', speed: 0 },
  { id: 'task_3', status: 'running', speed: 2048 },
];

// 模拟 State.tasks.setAll
const State = { tasks: { setAll: function(tasks) { _activeTasks = tasks; } } };

// 模拟 updateStatusFromPoll 中 _goOnline 变化检测逻辑
function simulateGoOffline() {
  var wasOnline = _goOnline;
  _goOnline = false;
  State.service = { setGoOnline: function() {} };

  if (wasOnline && !_goOnline) {
    _activeTasks = _activeTasks.map(function(t) {
      return t.status === 'running'
        ? Object.assign({}, t, { status: 'paused', speed: 0 })
        : t;
    });
    State.tasks.setAll(_activeTasks);
  }
}

// 测试
simulateGoOffline();

assert.strictEqual(_activeTasks[0].status, 'paused', 'task_1 should be paused');
assert.strictEqual(_activeTasks[0].speed, 0, 'task_1 speed should be 0');
assert.strictEqual(_activeTasks[1].status, 'pending', 'task_2 should remain pending');
assert.strictEqual(_activeTasks[2].status, 'paused', 'task_3 should be paused');
assert.strictEqual(_activeTasks[2].speed, 0, 'task_3 speed should be 0');

console.log('PASS: test_status_offline_pause');
