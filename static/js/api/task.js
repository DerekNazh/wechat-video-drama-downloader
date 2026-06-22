// ==================== 任务 API ====================
// 后端: /api/task/*

// GET /api/task/list - 获取任务列表
async function getTaskList() {
  const res = await fetch("/api/task/list");
  return res.json();
}

// POST /api/task/cancel - 取消任务（需要 task_id）
async function cancelTask(taskId) {
  const res = await fetch("/api/task/cancel", {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId })
  });
  return res.json();
}

// POST /api/task/cancel-all - 取消所有任务
async function cancelAllTasks() {
  const res = await fetch("/api/task/cancel-all", { method: 'POST' });
  return res.json();
}

// DELETE /api/task/{task_id} - 删除任务
async function deleteTask(taskId) {
  const res = await fetch("/api/task/" + taskId, { method: 'DELETE' });
  return res.json();
}

// GET /api/task/completion-log - 获取任务完成记录
async function fetchCompletionLog(limit, offset) {
  limit = limit || 50;
  offset = offset || 0;
  try {
    var res = await fetch('/api/task/completion-log?limit=' + limit + '&offset=' + offset);
    var data = await res.json();
    if (data.code === 0) {
      State.logs.setLogs(data.data);
      if (typeof renderHistoryList === 'function') {
        renderHistoryList();
      }
    }
  } catch (e) {
    console.warn('获取下载记录失败:', e);
  }
}