# 前端修改流程

## 短剧嗅探前端（Vue3）

1. 改源码：编辑 `F:\setup_temp\剪辑合成拆散\pac版本\frontend\src\` 下对应组件
2. 构建：在 `pac版本\frontend` 目录执行 `npm run build`
3. 覆盖：将 `pac版本\frontend\dist\` 整体覆盖到 `新_二合一总下载器\static\sniff\`（含 index.html，它引用带hash的JS/CSS文件名，每次构建会变）
4. 验证：启动项目，切换到短剧下载 Tab 测试

## 视频号监控前端（原生JS）

1. 直接改 `新_二合一总下载器\static\js\` 下对应文件
2. 刷新浏览器即可，无需构建
