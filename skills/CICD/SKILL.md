# CICD 发布流程

1. 更新版本：`python build.py --version x.y.z`，版本号写入 config/.env
2. 短剧前端有改动：按 skills/frontend_modify/SKILL.md 构建→覆盖 static/sniff/
3. 停止应用：关闭正在运行的微信信号视频短剧下载器
4. 打包：`.venv\Scripts\python build.py`，产物在 dist/ 下
5. 测试：运行 dist/ 下的 exe，验证视频号+短剧两个功能
6. 存档：`git add -A && git commit -m "release: vx.y.z 描述"`
7. 同步：`git push origin master` 推送到 GitHub 远程仓库
