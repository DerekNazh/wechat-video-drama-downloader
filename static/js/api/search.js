// ==================== 搜索 API ====================
// 后端: /api/search/*

// POST /api/search/author/add - 添加作者
export async function addAuthor(data) {
  const res = await fetch("/api/search/author/add", {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  return res.json();
}

// POST /api/search/author/batch-add - 批量添加作者
export async function batchAddAuthors(data) {
  const res = await fetch("/api/search/author/batch-add", {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  return res.json();
}