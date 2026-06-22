// global.js - 自定义下载文件名
// 在文件名前面添加发布时间（格式：YYYY.MM.DD）

function beforeFilename(filename, params) {
  // params 包含以下字段：
  // - filename: 默认文件名
  // - id: 视频id
  // - title: 视频标题
  // - spec: 视频质量（如 xWT111）
  // - created_at: 视频发布时间（Unix时间戳，单位秒）
  // - download_at: 视频下载时间（Unix时间戳，单位秒）
  // - author: up主名称
  
  // 如果有发布时间，添加到文件名前面
  if (params.created_at) {
    var date = new Date(params.created_at * 1000);
    var year = date.getFullYear();
    var month = ('0' + (date.getMonth() + 1)).slice(-2);
    var day = ('0' + date.getDate()).slice(-2);
    var dateStr = year + '.' + month + '.' + day;
    
    // 返回新文件名：日期_原标题
    return dateStr + '_' + filename;
  }
  
  // 如果没有发布时间，返回原文件名
  return filename;
}
