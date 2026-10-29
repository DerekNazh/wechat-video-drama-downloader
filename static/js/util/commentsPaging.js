// 评论分页 + 作者资料缓存（YZPQ-323）纯逻辑。
// 评论默认 1 页 20 条，加载更多翻页；作者资料缓存 7 天。无 DOM/网络依赖，Node 可单测。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.CommentPager = factory();
})(typeof self !== "undefined" ? self : this, function () {
  var PAGE_SIZE = 20;
  var PROFILE_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 天

  // 返回当前页（page 从 1 开始）应请求的偏移量与是否还有下一页。
  function pageInfo(page, total) {
    page = Math.max(1, page | 0);
    total = Math.max(0, total | 0);
    var start = (page - 1) * PAGE_SIZE;
    var hasMore = start < total;
    return { page: page, size: PAGE_SIZE, start: start, hasMore: hasMore,
             nextPage: hasMore ? page + 1 : page };
  }

  // 缓存是否命中：存了 data 且未过 TTL。now 注入便于单测。
  function isFresh(savedAt, now, ttl) {
    if (ttl === undefined) ttl = PROFILE_TTL_MS;
    if (savedAt === null || savedAt === undefined) return false;
    return (now - savedAt) < ttl;
  }

  return { PAGE_SIZE: PAGE_SIZE, PROFILE_TTL_MS: PROFILE_TTL_MS,
           pageInfo: pageInfo, isFresh: isFresh };
});
