// 格式化工具
function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  }
  return `${m}:${String(s).padStart(2,'0')}`;
}

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let idx = 0;
  let size = bytes;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx++;
  }
  return `${size.toFixed(1)} ${units[idx]}`;
}

function formatDate(timestamp) {
  if (!timestamp) return '';
  let d;
  if (typeof timestamp === 'string' && timestamp.includes('-')) {
    d = new Date(timestamp);
  } else {
    d = new Date(timestamp * 1000);
  }
  if (isNaN(d.getTime())) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatRelativeTime(isoTime) {
  if (!isoTime) return '';
  var now = Date.now();
  var then = new Date(isoTime).getTime();
  if (isNaN(then)) return '';
  var diff = now - then;
  var seconds = Math.floor(diff / 1000);
  if (seconds < 60) return '刚刚';
  var minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + ' 分钟前';
  var hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + ' 小时前';
  var days = Math.floor(hours / 24);
  if (days < 7) return days + ' 天前';
  return formatDate(isoTime);
}