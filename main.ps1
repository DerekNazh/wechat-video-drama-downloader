# 设置编码为 UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

# 获取脚本所在目录（避免硬编码路径）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 激活虚拟环境并运行
& ".\.venv\Scripts\Activate.ps1"
python main.py
