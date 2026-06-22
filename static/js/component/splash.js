// 开屏弹窗组件

/**
 * 显示开屏弹窗
 */
function showSplashDialog(config) {
  if (!config || !config.show) return;

  const overlay = document.createElement('div');
  overlay.className = 'splash-overlay';
  overlay.innerHTML = `
    <div class="splash-dialog">
      <img class="splash-qrcode" src="${config.qrcode_url}" alt="二维码">
      <div class="splash-title">关注公众号</div>
      <div class="splash-desc">扫码关注，获取最新更新与技术分享</div>
      <button class="splash-close" id="splashClose">关闭</button>
    </div>
  `;

  document.body.appendChild(overlay);

  // 点击关闭按钮
  overlay.querySelector('#splashClose').addEventListener('click', () => {
    overlay.remove();
  });

  // 点击遮罩层关闭
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.remove();
    }
  });
}

/**
 * 加载并显示开屏弹窗
 */
function loadSplash() {
  fetch('/api/leader/splash')
    .then(r => r.json())
    .then(data => {
      if (data.code === 0 && data.data) {
        showSplashDialog(data.data);
      }
    })
    .catch(err => {
      console.error('[Splash] 加载失败:', err);
    });
}