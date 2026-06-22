// ==================== 视频 API ====================
// 后端: /api/video/*

// GET /api/video/all - 获取所有作者及其视频
export async function getAllAuthorsWithVideos() {
  const res = await fetch("/api/video/all");
  return res.json();
}

// GET /api/video/author/{author_id} - 获取指定作者的所有视频
// videoType: 可选，'short_video' | 'live_replay'，不传则返回全部
export async function getAuthorVideos(authorId, videoType) {
  let url = `/api/video/author/${authorId}`;
  if (videoType) {
    url += `?video_type=${encodeURIComponent(videoType)}`;
  }
  const res = await fetch(url);
  return res.json();
}

// GET /api/video/{video_id} - 获取视频详情
export async function getVideoDetail(videoId) {
  const res = await fetch(`/api/video/${videoId}`);
  return res.json();
}

// POST /api/video/author/{author_id}/add - 新增作者最新视频
export async function addAuthorLatestVideos(authorId, data = {}) {
  const res = await apiFetch(`/api/video/author/${authorId}/add`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  return res.json();
}

// POST /api/video/add-all - 新增所有作者最新视频
export async function addAllAuthorsLatestVideos() {
  const res = await apiFetch('/api/video/add-all', { method: 'POST' });
  return res.json();
}

// DELETE /api/video/{video_id} - 删除视频
export async function deleteVideo(videoId) {
  const res = await fetch(`/api/video/${videoId}`, { method: 'DELETE' });
  return res.json();
}

// POST /api/video/batch-delete - 批量删除视频
export async function batchDeleteVideos(videoIds) {
  const res = await fetch('/api/video/batch-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_ids: videoIds })
  });
  return res.json();
}

// DELETE /api/video/author/{author_id}/all - 删除作者所有视频
export async function deleteAuthorAllVideos(authorId) {
  const res = await fetch(`/api/video/author/${authorId}/all`, { method: 'DELETE' });
  return res.json();
}