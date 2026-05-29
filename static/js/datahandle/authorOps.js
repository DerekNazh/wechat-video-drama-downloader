// 作者操作数据处理
async function importCSVAuthors() {
  const file = getSelectedCSVFile();
  const importBtn = document.getElementById('btnImportCSV');

  if (!file) {
    showToast({ type: 'warning', title: '请选择 CSV 文件', message: '请先选择要导入的 .csv 文件' });
    return;
  }

  if (!file.name.toLowerCase().endsWith('.csv')) {
    showToast({ type: 'warning', title: '文件格式不支持', message: '仅支持上传 .csv 文件' });
    return;
  }

  if (file.size <= 0) {
    showToast({ type: 'warning', title: '文件为空', message: '请选择包含作者数据的 CSV 文件' });
    return;
  }

  const formData = new FormData();
  formData.append('file', file, file.name);

  if (importBtn) {
    importBtn.disabled = true;
    importBtn.classList.add('btn-loading');
  }

  ImportModal.open('CSV 导入');
  ImportModal.setStep('parse');
  ImportModal.setLabel('正在上传文件...');

  try {
    ImportModal.setProgress(10);
    const uploadRes = await apiFetch('/api/inputer/upload-csv', {
      method: 'POST',
      body: formData,
    });
    if (!uploadRes.ok) {
      ImportModal.close();
      showToast({ type: 'error', title: '上传失败', message: `服务器返回 ${uploadRes.status}` });
      return;
    }
    const uploadData = await uploadRes.json();
    if (uploadData.code !== 0 || !uploadData.data?.file_path) {
      ImportModal.close();
      showToast({ type: 'error', title: '上传失败', message: uploadData.msg || '文件上传失败' });
      return;
    }

    ImportModal.setProgress(30);
    ImportModal.setStep('validate');
    ImportModal.setLabel('正在触发导入...');

    const res = await apiFetch('/api/inputer/csv/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: uploadData.data.file_path })
    });

    if (!res.ok) {
      ImportModal.close();
      showToast({ type: 'error', title: '导入失败', message: `服务器返回 ${res.status}` });
      return;
    }

    const data = await res.json();
    if (data.code !== 0) {
      ImportModal.close();
      showToast({ type: 'warning', title: '导入未开始', message: data.msg || '请检查 CSV 文件内容' });
      return;
    }

    // API 已触发，进度由 SSE import_progress 事件驱动
    showToast({ type: 'info', title: '导入已开始', message: '进度将通过实时推送更新' });

  } catch (e) {
    console.error('importCSVAuthors:', e);
    ImportModal.close();
    if (e.message && e.message.includes('UPLOAD_FILE_CHANGED')) {
      showToast({ type: 'warning', title: '文件已变更', message: '文件内容已修改，请重新选择文件' });
      resetCSVImportState();
    } else {
      showToast({ type: 'error', title: '导入失败', message: e.message || '网络错误，请稍后重试' });
    }
  } finally {
    if (importBtn) {
      importBtn.disabled = false;
      importBtn.classList.remove('btn-loading');
    }
    if (typeof resetCSVImportState === 'function') {
      resetCSVImportState();
    }
  }
}

async function importExcelAuthors() {
  const fileInput = document.getElementById('excelFileInput');
  const file = fileInput?.files?.[0];
  const importBtn = document.getElementById('btnImportExcel');

  if (!file) {
    showToast({ type: 'warning', title: '请选择文件', message: '请先选择要导入的 Excel 文件' });
    return;
  }

  if (!file.name.toLowerCase().endsWith('.xlsx') && !file.name.toLowerCase().endsWith('.xls')) {
    showToast({ type: 'warning', title: '文件格式不支持', message: '仅支持 .xlsx 或 .xls 文件' });
    return;
  }

  if (file.size <= 0) {
    showToast({ type: 'warning', title: '文件为空', message: '请选择包含作者数据的 Excel 文件' });
    return;
  }

  const formData = new FormData();
  formData.append('file', file, file.name);

  if (importBtn) {
    importBtn.disabled = true;
    importBtn.classList.add('btn-loading');
  }

  ImportModal.open('Excel 导入');
  ImportModal.setStep('parse');
  ImportModal.setLabel('正在上传文件...');

  try {
    ImportModal.setProgress(10);
    const uploadRes = await apiFetch('/api/inputer/upload-excel', {
      method: 'POST',
      body: formData,
    });
    if (!uploadRes.ok) {
      ImportModal.close();
      showToast({ type: 'error', title: '上传失败', message: `服务器返回 ${uploadRes.status}` });
      return;
    }
    const uploadData = await uploadRes.json();
    if (uploadData.code !== 0 || !uploadData.data?.file_path) {
      ImportModal.close();
      showToast({ type: 'error', title: '上传失败', message: uploadData.msg || '文件上传失败' });
      return;
    }

    ImportModal.setProgress(30);
    ImportModal.setStep('validate');
    ImportModal.setLabel('正在触发导入...');

    const res = await apiFetch('/api/inputer/excel/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: uploadData.data.file_path })
    });

    if (!res.ok) {
      ImportModal.close();
      showToast({ type: 'error', title: '导入失败', message: `服务器返回 ${res.status}` });
      return;
    }

    const data = await res.json();
    if (data.code !== 0) {
      ImportModal.close();
      showToast({ type: 'warning', title: '导入未开始', message: data.msg || '请检查 Excel 文件内容' });
      return;
    }

    showToast({ type: 'info', title: '导入已开始', message: '进度将通过实时推送更新' });

  } catch (e) {
    console.error('importExcelAuthors:', e);
    ImportModal.close();
    showToast({ type: 'error', title: '导入失败', message: e.message || '网络错误，请稍后重试' });
  } finally {
    if (importBtn) {
      importBtn.disabled = false;
      importBtn.classList.remove('btn-loading');
    }
  }
}

async function importFromTencentDoc() {
  const docUrl = document.getElementById('tencentDocUrl')?.value?.trim() || '';
  const clientId = document.getElementById('tencentClientId')?.value?.trim() || '';
  const accessToken = document.getElementById('tencentAccessToken')?.value?.trim() || '';
  const openId = document.getElementById('tencentOpenId')?.value?.trim() || '';

  if (!docUrl) {
    showToast({ type: 'warning', title: '请填写腾讯文档地址', message: '请输入腾讯文档的分享链接' });
    return;
  }

  if (!clientId || !accessToken || !openId) {
    showToast({ type: 'warning', title: '请填写完整凭证', message: 'Client ID、Access Token、Open ID 均为必填' });
    return;
  }

  const btn = document.getElementById('btnImportTencentDoc');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-loading');
  }

  ImportModal.open('腾讯文档导入');
  ImportModal.setStep('parse');
  ImportModal.setLabel('正在读取文档...');

  try {
    ImportModal.setProgress(15);

    const res = await apiFetch('/api/inputer/tencent-doc/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_url: docUrl, client_id: clientId, access_token: accessToken, openid: openId })
    });

    if (!res.ok) {
      ImportModal.close();
      showToast({ type: 'error', title: '导入失败', message: `服务器返回 ${res.status}` });
      return;
    }

    const data = await res.json();

    if (data.code === 0) {
      showToast({ type: 'info', title: '导入已开始', message: '进度将通过实时推送更新' });
    } else {
      ImportModal.close();
      showToast({ type: 'error', title: '导入失败', message: data.msg || '未知错误' });
    }
  } catch (e) {
    console.error('importFromTencentDoc:', e);
    ImportModal.close();
    showToast({ type: 'error', title: '导入失败', message: e.message || '网络错误' });
  } finally {
    if (btn) {
      btn.classList.remove('btn-loading');
      btn.disabled = false;
    }
  }
}

function searchAuthors() {
  const input = document.getElementById("searchInput");
  const q = input.value.trim();
  const el = document.getElementById("searchResults");

  if (!q) {
    showImportCards();
    return;
  }

  document.getElementById('importCards').style.display = 'none';
  document.getElementById('csvImportPanel').style.display = 'none';
  document.getElementById('excelImportPanel').style.display = 'none';
  document.getElementById('tencentDocImportPanel').style.display = 'none';
  const resultsList = document.getElementById('searchResultsList');
  resultsList.style.display = 'block';
  resultsList.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-tertiary)">搜索中...</div>';

  fetchWithErrorHandling(`/api/search/authors?q=${encodeURIComponent(q)}`, {}, '搜索作者')
    .then(data => {
      if (!data) return;

      const results = (data.data || []).map(item => {
        return {
          username: item.username || '',
          nickname: item.nickname || '',
          head_url: item.head_url || '',
          profession: '',
          signature: item.signature || '',
        };
      });
      if (results.length === 0) {
        resultsList.innerHTML = `
          <div class="search-hint">
            <div class="hint-icon">∅</div>
            <p>未找到相关作者</p>
            <span>请尝试其他关键词</span>
          </div>
        `;
        return;
      }

      const existingUsernames = new Set(_allAuthors.map(a => a.username));

      const escAttr = (s) => (s || '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/\n/g, ' ')
        .replace(/\r/g, '');

      let html = '';
      results.forEach(r => {
        const isAdded = existingUsernames.has(r.username);
        const avatarHtml = r.head_url
          ? `<img src="${r.head_url}" onerror="this.style.display='none'">`
          : '<div class="avatar-placeholder">?</div>';

        const tagHtml = r.profession
          ? `<span class="result-tag">${r.profession}</span>`
          : '';

        const escHtml = (s) => (s || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;')
          .replace(/\n/g, '<br>');
        const sigHtml = r.signature
          ? `<div class="result-signature">${escHtml(r.signature)}</div>`
          : '';

        const followHtml = r.friend_count
          ? `<span class="result-follow">${r.friend_count} 位好友关注</span>`
          : '';

        html += `
          <div class="search-result-card">
            <div class="result-avatar">${avatarHtml}</div>
            <div class="result-info">
              <div class="result-header">
                <div class="result-name">${escHtml(r.nickname || '未知')}</div>
                ${tagHtml}
              </div>
              ${sigHtml}
              <div class="result-meta">${followHtml}</div>
              <div class="result-hint">添加后将同步短视频 + 直播回放</div>
            </div>
            <button class="result-add-btn ${isAdded ? 'added' : ''}"
                    id="addBtn-${r.username.replace(/@/g, '_')}"
                    data-username="${escAttr(r.username)}"
                    data-nickname="${escAttr(r.nickname)}"
                    ${isAdded ? 'disabled' : ''}
                    onclick="addAuthorFromButton(this)">
              ${isAdded ? '已添加' : '添加'}
            </button>
          </div>
        `;
      });

      resultsList.innerHTML = html;

      resultsList.querySelectorAll('.result-add-btn').forEach((btn, i) => {
        const r = results[i];
        if (r) {
          btn.dataset.headurl = r.head_url || '';
          btn.dataset.profession = r.profession || '';
        }
      });
    });
}

function addAuthorFromButton(btn) {
  const username = btn.dataset.username;
  const nickname = btn.dataset.nickname;
  const headUrl = btn.dataset.headurl;
  const profession = btn.dataset.profession;
  const signatureEl = btn.closest('.search-result-card')?.querySelector('.result-signature');
  const signature = signatureEl ? signatureEl.textContent.trim() : '';

  showSyncOptionsDialog(username, nickname, headUrl, profession, signature, btn);
}

// 刷新作者列表
async function refreshAuthors() {
  try {
    await loadAllDataFromBackend();
    renderAuthorGrid(_allAuthors);
  } catch(e) {
    console.error("refreshAuthors:", e);
    renderAuthorGrid(_allAuthors);
  }
}

// 增量更新作者列表（避免全量重渲染）
async function refreshAuthorsIncremental() {
  try {
    await loadAllDataFromBackend();

    const newAuthors = _allAuthors;
    const newCatalog = _catalogData;

    // 检查作者列表是否有变化
    const oldUsernames = _allAuthors.map(a => a.username).sort().join(',');
    const newUsernames = newAuthors.map(a => a.username).sort().join(',');

    // 更新数据
    _allAuthors = newAuthors;
    _catalogData = newCatalog;
    State.authors.setAll(_allAuthors);
    State.catalog.setAll(_catalogData);

    // 如果作者列表变化或当前有筛选，重新筛选渲染
    if (oldUsernames !== newUsernames || _currentAuthorFilter !== 'all') {
      filterAuthors(_currentAuthorFilter);
      return;
    }

    // 全部筛选模式下，局部更新每个卡片
    const catMap = {};
    _catalogData.forEach(c => { catMap[c.username] = c; });

    _allAuthors.forEach(author => {
      const card = document.querySelector(`.author-card[onclick*="${author.username}"]`);
      if (!card) return;

      const cat = catMap[author.username] || {};
      // 使用分类统计字段
      const shortVideoCount = cat.short_video_count || 0;
      const replayCount = cat.replay_count || 0;
      const shortVideoDownloaded = cat.short_video_downloaded || 0;
      const replayDownloaded = cat.replay_downloaded || 0;
      const total = shortVideoCount + replayCount;
      const downloaded = shortVideoDownloaded + replayDownloaded;
      const pending = cat.pending || 0;
      const progress = cat.progress || 0;

      // 更新统计数字（使用分类统计格式：已下载/总数）
      const statValues = card.querySelectorAll('.stat-item .value');
      if (statValues.length >= 2) {
        // 短视频: "已下载/总数"
        const shortVideoText = `${shortVideoDownloaded}/${shortVideoCount}`;
        if (statValues[0].textContent !== shortVideoText) {
          statValues[0].textContent = shortVideoText;
        }
        // 直播回放: "已下载/总数"
        const replayText = `${replayDownloaded}/${replayCount}`;
        if (statValues[1].textContent !== replayText) {
          statValues[1].textContent = replayText;
        }
      }

      // 更新进度条
      const progressFill = card.querySelector('.author-progress-fill');
      const progressText = card.querySelector('.author-progress-text');
      if (progressFill) progressFill.style.width = `${progress}%`;
      if (progressText) progressText.textContent = `${progress}% 完成`;

      // 更新状态标签（只改文字和 class，不重建 DOM）
      const statusBadge = card.querySelector('.author-status');
      if (statusBadge) {
        let statusClass = 'idle';
        let statusText = '空闲';
        if (author.status === 'downloading') {
          statusClass = 'downloading';
          statusText = '下载中';
        } else if (pending === 0 && total > 0) {
          statusClass = 'done';
          statusText = '已完成';
        }
        if (statusBadge.className !== `author-status ${statusClass}`) {
          statusBadge.className = `author-status ${statusClass}`;
          const dot = statusBadge.querySelector('.dot');
          if (dot) {
            dot.className = statusClass === 'downloading' ? 'dot green' : 'dot';
          } else {
            statusBadge.textContent = '';
            const newDot = document.createElement('span');
            newDot.className = statusClass === 'downloading' ? 'dot green' : 'dot';
            statusBadge.appendChild(newDot);
          }
          // 更新文字节点（dot 后面的文本）
          const textNode = statusBadge.childNodes[statusBadge.childNodes.length - 1];
          if (textNode && textNode.nodeType === Node.TEXT_NODE) {
            textNode.textContent = statusText;
          } else {
            statusBadge.appendChild(document.createTextNode(statusText));
          }
        }
      }

      // 更新卡片下载中状态
      card.classList.toggle('downloading', author.status === 'downloading');
    });

  } catch(e) {
    console.error("refreshAuthorsIncremental:", e);
  }
}