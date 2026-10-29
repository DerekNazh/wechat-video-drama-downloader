// 合集入口可见性 + 合集内视频可下载过滤（YZPQ-324）纯逻辑。
// 作者有合集才显示入口；合集内视频过滤出可下载项。无 DOM/网络依赖，Node 可单测。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.CollectionEntry = factory();
})(typeof self !== "undefined" ? self : this, function () {
  // collections: fetch_user_collections 返回的数组。有至少 1 个合集才显示入口。
  function shouldShowEntry(collections) {
    return Array.isArray(collections) && collections.length > 0;
  }

  // videos: fetch_collection_videos 返回的数组。过滤出可下载项（有 id 且未标记不可下载）。
  function downloadableVideos(videos) {
    if (!Array.isArray(videos)) return [];
    return videos.filter(function (v) {
      if (!v || v.id === undefined || v.id === null || v.id === "") return false;
      if (v.downloadable === false) return false;
      return true;
    });
  }

  return { shouldShowEntry: shouldShowEntry, downloadableVideos: downloadableVideos };
});
