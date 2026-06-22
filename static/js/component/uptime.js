// 运行时长显示组件
let _appStartTime = 0;

function startUptimeTimer() {
  _appStartTime = Date.now();
  function update() {
    const elapsed = Math.floor((Date.now() - _appStartTime) / 1000);
    const h = Math.floor(elapsed / 3600);
    const m = Math.floor((elapsed % 3600) / 60);
    const s = elapsed % 60;
    document.getElementById("txtUptime").textContent =
      `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  }
  update();
  setInterval(update, 1000);
}