// 日志组件
let _lastLogCount = 0;

async function refreshLogs() {
  try {
    const res = await fetch("/api/service/logs");
    const data = await res.json();
    const logs = data.logs || [];
    const el = document.getElementById("logBody");

    document.getElementById("logBadge").textContent = logs.length + " 条";

    if (logs.length === 0) {
      el.innerHTML = '<div class="log-empty">等待启动...</div>';
      return;
    }

    if (logs.length > _lastLogCount) {
      el.innerHTML = '';
      logs.forEach(l => {
        const msgCls = l.level === 'success' || l.level === 'info' ? 'msg-success'
          : l.level === 'error' ? 'msg-error'
          : l.level === 'warning' ? 'msg-warn' : 'msg-default';

        const div = document.createElement('div');
        div.className = 'log-line';
        div.innerHTML = `<span class="time">${l.time || ''}</span><span class="${msgCls}">${l.message || ''}</span>`;
        el.appendChild(div);
      });
    }
    _lastLogCount = logs.length;

  } catch(e) { console.error("refreshLogs:", e); }
}

function toggleLogPanel() {
  document.getElementById("logPanel").classList.toggle("collapsed");
}