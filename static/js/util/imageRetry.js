// 封面/头像图片加载失败重试策略（YZPQ-325）：失败重试 ≤3 次，超限后稳定占位。
// 纯函数，无 DOM 依赖，可在 Node 下单测。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ImageRetry = factory();
})(typeof self !== "undefined" ? self : this, function () {
  var MAX_RETRIES = 3;

  // attempt 从 0 开始（当前为第几次失败后）。返回是否还应继续重试。
  function shouldRetry(attempt, max) {
    if (max === undefined) max = MAX_RETRIES;
    if (attempt < 0) attempt = 0;
    return attempt < max;
  }

  // 退避等待毫秒：指数 200/400/800ms，封顶 1000ms。
  function nextBackoff(attempt) {
    return Math.min(1000, 200 * Math.pow(2, Math.max(0, attempt)));
  }

  // 超限稳定占位：按图片种类返回占位资源标识（DOM 层再映射到真实图）。
  function placeholderFor(kind) {
    if (kind === "avatar") return "placeholder-avatar";
    return "placeholder-cover";
  }

  return { MAX_RETRIES: MAX_RETRIES, shouldRetry: shouldRetry, nextBackoff: nextBackoff, placeholderFor: placeholderFor };
});
