// ==================== 导入 API ====================
// 后端: /api/inputer/*

// POST /api/inputer/csv/import - CSV 导入
export async function importCSV(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await apiFetch("/api/inputer/csv/import", {
    method: 'POST',
    body: formData
  });
  return res.json();
}

// POST /api/inputer/excel/import - Excel 导入
export async function importExcel(data) {
  const res = await apiFetch("/api/inputer/excel/import", {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  return res.json();
}

// POST /api/inputer/tencent-doc/import - 腾讯文档导入
export async function importTencentDoc(data) {
  const res = await apiFetch("/api/inputer/tencent-doc/import", {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  return res.json();
}