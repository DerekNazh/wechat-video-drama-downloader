// 互动数格式化（YZPQ-318）：0 值正常显示；过万缩写为 x.x 万，过亿为 x.x 亿。
// 纯函数，无 DOM 依赖，可在 Node 下单测。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.FormatCount = factory();
})(typeof self !== "undefined" ? self : this, function () {
  function round1(v) {
    return Math.round(v * 10) / 10;
  }
  function formatCount(n) {
    if (n === null || n === undefined || isNaN(n)) return "0";
    n = Number(n);
    if (n < 0) n = 0;
    if (n < 10000) return String(Math.floor(n));
    if (n < 100000000) {
      var w = round1(n / 10000);
      return (w % 1 === 0 ? w.toFixed(0) : w.toFixed(1)) + "万";
    }
    var y = round1(n / 100000000);
    return (y % 1 === 0 ? y.toFixed(0) : y.toFixed(1)) + "亿";
  }
  // 列表卡片展示：点赞 + 评论 2 项；详情页：read/like/fav/forward/comment 5 项
  var LIST_FIELDS = ["like", "comment"];
  var DETAIL_FIELDS = ["read", "like", "fav", "forward", "comment"];
  return { formatCount: formatCount, LIST_FIELDS: LIST_FIELDS, DETAIL_FIELDS: DETAIL_FIELDS };
});
