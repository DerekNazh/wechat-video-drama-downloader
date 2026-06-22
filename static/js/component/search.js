// 搜索与导入组件

// pywebview 下载回调（由 gui.py 的 evaluate_js 调用）
window._downloadCallback = function(result) {
  if (result && result.success) {
    showToast({ type: 'success', title: '下载成功', message: result.message });
  } else {
    showToast({ type: 'error', title: '下载失败', message: result?.message || '未知错误' });
  }
};

function openSearchPage() {
  navigateTo('search');
  showImportCards();
  // 进入搜索页面时检查监控状态，更新卡片样式
  if (typeof DocSyncMonitor !== 'undefined' && DocSyncMonitor.loadStatus) {
    DocSyncMonitor.loadStatus();
  }
}

function getSelectedCSVFile() {
  const fileInput = document.getElementById('csvFileInput');
  const file = fileInput?.files?.[0] || null;
  return file;
}

function resetCSVImportState() {
  const fileInput = document.getElementById('csvFileInput');
  if (fileInput) {
    fileInput.value = '';
  }

  // 恢复上传区域、隐藏文件卡片
  const uploadZone = document.getElementById('csvUploadZone');
  if (uploadZone) {
    uploadZone.style.display = 'flex';
  }

  const fileCard = document.getElementById('csvFileCard');
  if (fileCard) {
    fileCard.style.display = 'none';
  }

  // 重置文件卡片内容
  const fileName = document.getElementById('csvFileName');
  const fileMeta = document.getElementById('csvFileMeta');
  if (fileName) fileName.textContent = '未选择文件';
  if (fileMeta) fileMeta.textContent = '请选择 .csv 文件';

  updateImportButtons();
}

function showImportCards() {
  const importCards = document.getElementById('importCards');
  if (importCards) importCards.style.display = 'flex';

  document.getElementById('csvImportPanel').style.display = 'none';
  document.getElementById('excelImportPanel').style.display = 'none';
  document.getElementById('tencentDocImportPanel').style.display = 'none';

  const resultsList = document.getElementById('searchResultsList');
  if (resultsList) resultsList.style.display = 'none';
}

function showCSVImport() {
  document.getElementById('importCards').style.display = 'none';
  document.getElementById('csvImportPanel').style.display = 'block';
  document.getElementById('excelImportPanel').style.display = 'none';
  document.getElementById('tencentDocImportPanel').style.display = 'none';
}

function hideCSVImport() {
  document.getElementById('csvImportPanel').style.display = 'none';
  document.getElementById('importCards').style.display = 'flex';
}

function showExcelImport() {
  document.getElementById('importCards').style.display = 'none';
  document.getElementById('excelImportPanel').style.display = 'block';
  document.getElementById('csvImportPanel').style.display = 'none';
  document.getElementById('tencentDocImportPanel').style.display = 'none';
}

function hideExcelImport() {
  document.getElementById('excelImportPanel').style.display = 'none';
  document.getElementById('importCards').style.display = 'flex';
}

function showTencentDocImport() {
  // TDD: T2 - 监控中不能进入导入面板
  const checkResult = canEnterImportPanel();
  if (!checkResult.allowed) {
    showToast({
      type: 'info',
      title: '监控运行中',
      message: '请先停止监控后再进入导入面板'
    });
    return;
  }

  document.getElementById('importCards').style.display = 'none';
  document.getElementById('tencentDocImportPanel').style.display = 'block';
  document.getElementById('csvImportPanel').style.display = 'none';
  document.getElementById('excelImportPanel').style.display = 'none';
}

function canEnterImportPanel() {
  // 引用 DocSyncMonitor 的运行状态
  const isMonitoring = typeof DocSyncMonitor !== 'undefined' && DocSyncMonitor.isRunning();
  if (isMonitoring) {
    return { allowed: false, reason: 'monitoring_active' };
  }
  return { allowed: true, reason: '' };
}

function handleTencentDocCardClick() {
  // TDD: T1 - 监控中点击卡片触发停止，否则进入面板
  const isMonitoring = typeof DocSyncMonitor !== 'undefined' && DocSyncMonitor.isRunning();

  if (isMonitoring) {
    // 监控中 → 触发停止
    if (typeof toggleDocSync === 'function') {
      toggleDocSync();
    }
  } else {
    // 未监控 → 进入导入面板
    showTencentDocImport();
  }
}

function hideTencentDocImport() {
  document.getElementById('tencentDocImportPanel').style.display = 'none';
  document.getElementById('importCards').style.display = 'flex';
}

function triggerCSVFileSelect() {
  const fileInput = document.getElementById('csvFileInput');
  if (fileInput) {
    fileInput.click();
  }
}

function getSelectedExcelFile() {
  return document.getElementById('excelFileInput')?.files?.[0] || null;
}

function triggerExcelFileSelect() {
  document.getElementById('excelFileInput')?.click();
}

async function handleExcelFileChange(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  const info = document.getElementById('excelInfo');
  const fileName = document.getElementById('excelFileName');
  const fileCard = document.getElementById('excelFileCard');

  if (fileName) fileName.textContent = file.name;
  if (info) info.textContent = `${(file.size / 1024).toFixed(1)} KB`;
  if (fileCard) fileCard.style.display = 'flex';

  updateImportButtons();
}

function resetExcelImportState() {
  const fileInput = document.getElementById('excelFileInput');
  if (fileInput) fileInput.value = '';
  const fileCard = document.getElementById('excelFileCard');
  if (fileCard) fileCard.style.display = 'none';
  updateImportButtons();
}

async function handleCSVFileChange(event) {
  const file = event.target.files?.[0];

  if (!file) {
    return;
  }

  // 显示文件卡片、隐藏上传区域
  const uploadZone = document.getElementById('csvUploadZone');
  if (uploadZone) {
    uploadZone.style.display = 'none';
  }

  const fileCard = document.getElementById('csvFileCard');
  if (fileCard) {
    // HTML 元素 ID: csvFileName, csvFileMeta
    const fileNameEl = document.getElementById('csvFileName');
    const fileSizeEl = document.getElementById('csvFileMeta');
    if (fileNameEl) {
      fileNameEl.textContent = file.name;
    }
    if (fileSizeEl) {
      const sizeText = formatFileSize(file.size);
      fileSizeEl.textContent = sizeText;
    }
    fileCard.style.display = 'flex';
  }

  const reader = new FileReader();
  reader.onload = function(e) {
    const text = e.target?.result;
    const lines = text.split('\n').filter(line => line.trim());
    if (lines.length > 1) {
    }

    // 更新文件卡片显示数据行数
    const fileMeta = document.getElementById('csvFileMeta');
    if (fileMeta) {
      const infoText = `共 ${lines.length - 1} 条数据 · ${formatFileSize(file.size)}`;
      fileMeta.textContent = infoText;
    }

    updateImportButtons();
  };
  reader.onerror = function(e) {
    console.error('[CSV选择] FileReader 读取出错:', e);
  };
  reader.readAsText(file);
}

function clearSelectedCSV(event) {
  event.target.value = '';
  resetCSVImportState();
}

function downloadCSVTemplate() {
  // pywebview 环境使用原生 API（fetch+blob 在 pywebview 中无法触发下载）
  if (window.pywebview && window.pywebview.api && window.pywebview.api.download_template) {
    // 调用原生 API，结果通过 window._downloadCallback 回调
    window.pywebview.api.download_template();
    return;
  }
  // 浏览器环境使用 fetch+blob
  fetch('/api/inputer/csv/template')
    .then(r => {
      if (!r.ok) throw new Error(`下载模板失败: ${r.status}`);
      return r.blob();
    })
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'author_template.csv';
      a.click();
      URL.revokeObjectURL(url);
    })
    .catch(e => {
      console.error('downloadCSVTemplate:', e);
      showToast({ type: 'error', title: '下载模板失败', message: e.message });
    });
}

function downloadExcelTemplate() {
  // pywebview 环境使用原生 API
  if (window.pywebview && window.pywebview.api && window.pywebview.api.download_excel_template) {
    window.pywebview.api.download_excel_template();
    return;
  }
  // 浏览器环境使用 fetch+blob
  fetch('/api/inputer/excel/template')
    .then(r => {
      if (!r.ok) throw new Error(`下载模板失败: ${r.status}`);
      return r.blob();
    })
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'excel_template.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    })
    .catch(e => {
      console.error('downloadExcelTemplate:', e);
      showToast({ type: 'error', title: '下载模板失败', message: e.message });
    });
}

function showCSVImportResultDialog(result) {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-box">
      <div class="dialog-title">导入结果</div>
      <div class="dialog-content">
        <p>成功: <strong>${result.success}</strong></p>
        <p>失败: <strong>${result.failed}</strong></p>
      </div>
      <div class="dialog-buttons">
        <button class="btn-dialog primary" id="dlgClose">确定</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector('#dlgClose').addEventListener('click', () => closeDialog(overlay));
}

function updateImportButtons() {
  const csvBtn = document.getElementById('btnImportCSV');
  const excelBtn = document.getElementById('btnImportExcel');
  const docBtn = document.getElementById('btnImportTencentDoc');

  const csvFile = document.getElementById('csvFileInput')?.files?.[0];
  const excelFile = document.getElementById('excelFileInput')?.files?.[0];
  const hasDocUrl = !!document.getElementById('tencentDocUrl')?.value;


  if (csvBtn) {
    csvBtn.disabled = !csvFile;
  }
  if (excelBtn) {
    excelBtn.disabled = !excelFile;
  }
  if (docBtn) {
    docBtn.disabled = !hasDocUrl;
  }
}
