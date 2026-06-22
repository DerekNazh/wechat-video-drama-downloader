// ==================== 播放 API ====================
// 后端: /api/player/*

// POST /api/player/play - 播放视频
export async function playVideo(data) {
  const res = await fetch("/api/player/play", {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  return res.json();
}