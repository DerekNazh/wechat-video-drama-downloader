// 作者详情页全局进度条组件

// 辅助函数：获取当前作者+当前类型的正在下载数量
// 依赖全局变量 _activeTasks（由 SSE 推送维护的当前下载任务列表）
function getDownloadingCountForCurrentType() {
  if (typeof _activeTasks === 'undefined' || !_activeTasks) return 0;
  return _activeTasks.filter(function(t) {
    if (!t || !t.video_id) return false;
    var video = State.videos.get(State.videos.getAuthorByVideoId(t.video_id), t.video_id);
    if (!video) return false;
    var videoType = video.video_type || 'short_video';
    var videoAuthor = State.videos.getAuthorByVideoId(t.video_id);
    return videoType === _currentVideoType && videoAuthor === _currentAuthor.username;
  }).length;
}

// 更新作者详情页全局进度条
function updateAuthorGlobalProgress() {
  if (!_currentAuthor) return;
  var cat = _catalogData.find(function(c) {
    return c.username === _currentAuthor.username;
  });
  if (!cat) return;

  var isReplay = _currentVideoType === 'live_replay';
  var total = isReplay ? cat.replay_count : cat.short_video_count;
  var downloaded = isReplay ? cat.replay_downloaded : cat.short_video_downloaded;
  var percent = total > 0 ? Math.round((downloaded / total) * 100) : 0;

  // 进度条：0 个视频时隐藏进度条，只显示文字
  var barWrapper = document.querySelector('.author-progress-bar-wrapper');
  if (barWrapper) {
    barWrapper.style.display = total > 0 ? '' : 'none';
  }

  var fill = document.getElementById('authorProgressFill');
  if (fill) {
    fill.style.width = percent + '%';
    fill.classList.toggle('complete', percent === 100);
  }

  var shimmer = document.getElementById('authorProgressShimmer');
  var downloadingCount = getDownloadingCountForCurrentType();
  if (shimmer) {
    shimmer.classList.toggle('active', downloadingCount > 0);
  }

  var text = document.getElementById('authorProgressText');
  var typeName = isReplay ? '直播回放' : '短视频';
  if (text) {
    text.textContent = '已下载 ' + downloaded + '/' + total + ' 个' + typeName + ' (' + percent + '%)';
  }

  var dl = document.getElementById('authorProgressDownloading');
  if (dl) {
    if (downloadingCount > 0) {
      dl.classList.add('active');
      dl.innerHTML = '<span class="dot"></span> 正在下载 ' + downloadingCount + ' 个';
    } else {
      dl.classList.remove('active');
    }
  }
}
