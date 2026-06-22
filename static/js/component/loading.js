// Loading 动画组件
function startLoadingProgress() {
  const fill = document.getElementById("loadingProgressFill");
  const text = document.getElementById("loadingText");
  let progress = 0;
  const steps = [
    { p: 30, t: "连接后端..." },
    { p: 60, t: "加载作者数据..." },
    { p: 100, t: "完成" }
  ];
  let stepIdx = 0;

  function animate() {
    if (stepIdx >= steps.length) {
      setTimeout(() => {
        document.getElementById("loadingOverlay").classList.add("hidden");
      }, 200);
      return;
    }
    const target = steps[stepIdx].p;
    const interval = setInterval(() => {
      progress += 3;
      if (fill) fill.style.width = progress + "%";
      if (progress >= target) {
        if (text) text.textContent = steps[stepIdx].t;
        clearInterval(interval);
        stepIdx++;
        setTimeout(animate, 150);
      }
    }, 20);
  }
  animate();
}