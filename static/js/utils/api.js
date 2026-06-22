// API 请求封装：自动处理 503 等错误，给用户友好提示

const _503_MESSAGES = {
  '-1': '微信视频号后端服务未启动，请先启动服务',
  '-2': '微信客户端未连接，请打开微信并登录',
};

const _503_TITLES = {
  '-1': '服务未启动',
  '-2': '微信未连接',
};

async function apiFetch(url, options) {
  var resp = await fetch(url, options);

  if (resp.status === 503) {
    try {
      var data = await resp.json();
      var code = String(data.detail?.code ?? data.code ?? '');
      var msg = data.detail?.msg || data.msg || _503_MESSAGES[code] || '服务暂不可用，请稍后重试';
      var title = _503_TITLES[code] || '服务未就绪';
      showToast({ type: 'warning', title: title, message: msg, duration: 5000 });
    } catch (_) {
      showToast({ type: 'warning', title: '服务未就绪', message: '服务暂不可用，请稍后重试', duration: 5000 });
    }
    var err = new Error('503');
    err.status = 503;
    throw err;
  }

  if (!resp.ok) {
    var errText = '请求失败';
    try { var ej = await resp.json(); errText = ej.detail?.msg || ej.msg || errText; } catch(_) {}
    var err = new Error(errText);
    err.status = resp.status;
    throw err;
  }

  return resp;
}
