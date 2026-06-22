/**
 * 导入进度弹窗组件
 * 统一管理 CSV / Excel / 腾讯文档三种导入的进度展示
 */

const ImportModal = (() => {
  let _cancelled = false;
  const STEPS = ['parse', 'validate', 'import', 'save'];
  const STEP_NAMES = { parse: '解析文件', validate: '校验数据', import: '导入作者', save: '保存视频' };

  function el(id) {
    return document.getElementById(id);
  }

  function open(title) {
    _cancelled = false;
    const overlay = el('importModalOverlay');
    if (!overlay) return;

    const titleEl = el('importModalTitle');
    if (titleEl) titleEl.textContent = title || '正在导入';

    resetUI();
    showProgressView();
    overlay.classList.add('active');
  }

  function close() {
    const overlay = el('importModalOverlay');
    if (overlay) overlay.classList.remove('active');
  }

  function resetUI() {
    setProgress(0);
    setStep('parse');
    setCounts(0, 0, 0);
    setCurrentName('');
    const fill = el('importProgressFill');
    if (fill) fill.classList.remove('complete');
    const percent = el('importProgressPercent');
    if (percent) percent.classList.remove('complete');
  }

  function showProgressView() {
    const progress = el('importModalProgress');
    const result = el('importModalResult');
    if (progress) progress.style.display = '';
    if (result) result.style.display = 'none';
  }

  function showResultView(successCount, failCount, total, failures) {
    const progress = el('importModalProgress');
    const result = el('importModalResult');
    if (progress) progress.style.display = 'none';
    if (result) result.style.display = '';

    el('resultSuccessCount').textContent = successCount;
    el('resultFailCount').textContent = failCount;
    el('resultTotalCount').textContent = total;

    const failDetails = el('importFailDetails');
    const failList = el('importFailList');
    if (failCount > 0 && failures && failures.length > 0) {
      if (failDetails) failDetails.style.display = '';
      if (failList) {
        failList.innerHTML = failures.map((f, i) => `
          <div class="fail-item">
            <span class="fail-index">#${i + 1}</span>
            <span>${f.name || '未知'}</span>
            <span class="fail-reason">${f.reason || ''}</span>
          </div>
        `).join('');
      }
    } else {
      if (failDetails) failDetails.style.display = 'none';
    }

    const fill = el('importProgressFill');
    if (fill) fill.classList.add('complete');
    const percent = el('importProgressPercent');
    if (percent) percent.classList.add('complete');
  }

  function setProgress(value) {
    const fill = el('importProgressFill');
    const percent = el('importProgressPercent');
    const v = Math.min(100, Math.max(0, Math.round(value)));
    if (fill) fill.style.width = v + '%';
    if (percent) percent.textContent = v + '%';
  }

  function setStep(stepName) {
    const stepsContainer = el('importSteps');
    if (!stepsContainer) return;

    const idx = STEPS.indexOf(stepName);
    stepsContainer.querySelectorAll('.import-step').forEach((s, i) => {
      s.classList.remove('active', 'done');
      if (i < idx) s.classList.add('done');
      else if (i === idx) s.classList.add('active');
    });

    const label = el('importProgressLabel');
    if (label) label.textContent = STEP_NAMES[stepName] || '处理中...';
  }

  function setCounts(success, fail, total) {
    const s = el('importSuccessCount');
    const f = el('importFailCount');
    const t = el('importTotalCount');
    if (s) s.textContent = success;
    if (f) f.textContent = fail;
    if (t) t.textContent = total;
  }

  function setCurrentName(name) {
    const container = el('importCurrent');
    const nameEl = el('importCurrentName');
    if (!container) return;
    if (name) {
      container.style.display = '';
      if (nameEl) nameEl.textContent = name;
    } else {
      container.style.display = 'none';
    }
  }

  function setLabel(text) {
    const label = el('importProgressLabel');
    if (label) label.textContent = text;
  }

  function isCancelled() {
    return _cancelled;
  }

  function cancel() {
    _cancelled = true;
    setLabel('正在取消...');
  }

  function handleSSEProgress(data) {
    if (data.phase === 'start') {
      setCounts(0, 0, data.total);
      setStep('import');
      setLabel('正在导入作者...');
      setCurrentName('');
    } else if (data.phase === 'processing') {
      var pct = data.total > 0 ? Math.round(data.current / data.total * 100) : 0;
      setProgress(pct);
      setCounts(data.success, data.fail, data.total);
      setCurrentName(data.name);
    } else if (data.phase === 'done') {
      setProgress(100);
      showResultView(data.success, data.fail, data.total, []);
      if (data.success > 0 && typeof refreshAuthors === 'function') {
        refreshAuthors();
      }
    }
  }

  return {
    open,
    close,
    setProgress,
    setStep,
    setCounts,
    setCurrentName,
    setLabel,
    showResultView,
    isCancelled,
    cancel,
    handleSSEProgress,
    STEPS,
  };
})();

function closeImportModal() {
  ImportModal.close();
}

function cancelImport() {
  ImportModal.cancel();
}