$ErrorActionPreference = "Stop"

# 复用原会话目录、端口和密钥，让用户已有链接在服务恢复后直接重连。
$projectDir = "C:\Users\86181\Desktop\Python\LingJing_AI"
$sessionDir = Join-Path $projectDir ".superpowers\brainstorm\codex-20260722-173629"
$scriptDir = "C:\Users\86181\.codex\plugins\cache\openai-curated-remote\superpowers\6.1.1\skills\brainstorming\scripts"

$env:BRAINSTORM_DIR = $sessionDir
$env:BRAINSTORM_HOST = "127.0.0.1"
$env:BRAINSTORM_URL_HOST = "localhost"
$env:BRAINSTORM_PORT_FILE = Join-Path $projectDir ".superpowers\brainstorm\.last-port"
$env:BRAINSTORM_TOKEN_FILE = Join-Path $projectDir ".superpowers\brainstorm\.last-token"
$env:BRAINSTORM_OPEN = "1"
$env:BRAINSTORM_IDLE_TIMEOUT_MS = "86400000"

# 前台运行由计划任务托管，避免调用终端结束时子进程被一起回收。
& node (Join-Path $scriptDir "server.cjs") "--brainstorm-server-id=lingjing-visual-20260723"
