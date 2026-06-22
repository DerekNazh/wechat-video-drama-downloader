// ==================== 服务状态 ====================

var _svc_goOnline = false;
var _svc_serviceState = 'stopped';
var _svc_monitorRunning = false;
var _svc_wechatConnected = false;
var _svc_statusInterval = 5000;
var _svc_startTime = Date.now();

State.service = {
  // Go 后端
  setGoOnline: function(online) { _svc_goOnline = online; State.emit('service:goOnline', online); },
  isGoOnline: function() { return _svc_goOnline; },

  // 服务状态
  setServiceState: function(state) { _svc_serviceState = state; State.emit('service:stateChange', state); },
  getServiceState: function() { return _svc_serviceState; },

  // 监控
  setMonitorRunning: function(running) { _svc_monitorRunning = running; State.emit('service:monitorChange', running); },
  isMonitorRunning: function() { return _svc_monitorRunning; },

  // 微信连接
  setWechatConnected: function(connected) { _svc_wechatConnected = connected; State.emit('service:wechatChange', connected); },
  isWechatConnected: function() { return _svc_wechatConnected; },

  // 轮询间隔
  setStatusInterval: function(interval) { _svc_statusInterval = interval; },
  getStatusInterval: function() { return _svc_statusInterval; },

  // 运行时间
  getStartTime: function() { return _svc_startTime; }
};
