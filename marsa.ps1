<#
.SYNOPSIS
    MARSA agent 启动器 —— 一条命令让 agent 自己运转。

.EXAMPLE
    .\marsa.ps1 doctor
    检查环境（Python / 依赖 / 凭据 / 工具 / 技能 / 人格）。

.EXAMPLE
    .\marsa.ps1 run "用 ramsey_compare 比较 n=44 上的三个算子，各 3 个 seed、5 秒预算"
    以自主研究模式运行，默认 10 轮。

.EXAMPLE
    .\marsa.ps1 run "继续上一轮的工作" -Project ramsey_agent_run -Iterations 5
    接着已有项目继续跑（状态会延续）。

.EXAMPLE
    .\marsa.ps1 analyze
    分析最近一次运行的稳定性。
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",

    [Parameter(Position = 1)]
    [string]$Text = "",

    [int]$Iterations = 10,
    [string]$Project = ""
)

$ErrorActionPreference = "Stop"

$Root  = "D:\myagent"
$MHome = "D:\myagent\moonshine-home"
$Agent = "computational-construction-search"
$Py    = "C:\Users\26319\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if (-not (Test-Path $Py)) {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) { $Py = $found.Source }
    else { Write-Host "[错误] 找不到 Python。"; exit 1 }
}

function Write-Head($s) { Write-Host ""; Write-Host "=== $s ===" -ForegroundColor Cyan }
function Write-Ok($s)   { Write-Host "  [OK] $s" -ForegroundColor Green }
function Write-Bad($s)  { Write-Host "  [!!] $s" -ForegroundColor Red }
function Write-Info($s) { Write-Host "  $s" -ForegroundColor Gray }


function Invoke-Doctor {
    Write-Head "环境自检"
    $problems = 0

    if (Test-Path $Py) { Write-Ok "Python: $Py" }
    else { Write-Bad "找不到 Python"; $problems++ }

    $importCheck = & $Py -c "import moonshine, marsa, marsa.ops; print('ok')" 2>&1
    if ("$importCheck" -match '^ok') {
        Write-Ok "moonshine / marsa 可导入"
    } else {
        Write-Bad "moonshine 或 marsa 导入失败"
        Write-Info "修复：.\marsa.ps1 install"
        $problems++
    }

    $credCmd = "from moonshine.moonshine_constants import MoonshinePaths; " +
               "from moonshine.moonshine_cli.config import resolve_home; " +
               "from moonshine.credentials import get_stored_credential, mask_secret; " +
               "p = MoonshinePaths(resolve_home(r'" + $MHome + "')); " +
               "v = get_stored_credential(p, 'DEEPSEEK_API_KEY'); " +
               "print(mask_secret(v) if v else 'MISSING')"
    $cred = & $Py -c $credCmd 2>&1
    if ("$cred" -match '^sk-') { Write-Ok "API 凭据已配置（$cred）" }
    else { Write-Bad "API 凭据缺失"; Write-Info "修复：.\marsa.ps1 install"; $problems++ }

    $tools = (& $Py -m moonshine --home $MHome tools 2>&1 | Select-String 'ramsey_' | Measure-Object).Count
    if ($tools -ge 5) { Write-Ok "ramsey 工具 $tools 个已注册" }
    else { Write-Bad "ramsey 工具只有 $tools 个（应 5 个）"; Write-Info "修复：.\marsa.ps1 install"; $problems++ }

    $skills = (Get-ChildItem "$MHome\skills\installed" -Directory -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($skills -ge 4) { Write-Ok "技能 $skills 份已装载" }
    else { Write-Bad "技能只有 $skills 份（应 4 份）"; $problems++ }

    if (Test-Path "$MHome\agents\installed\$Agent\AGENT.md") {
        Write-Ok "agent 人格：$Agent"
    } else {
        Write-Bad "agent 人格缺失"; $problems++
    }

    Write-Host ""
    if ($problems -eq 0) {
        Write-Host "环境就绪。直接跑：" -ForegroundColor Green
        Write-Host '  .\marsa.ps1 run "你想让它研究什么"' -ForegroundColor White
    } else {
        Write-Host "有 $problems 项问题，先执行 .\marsa.ps1 install" -ForegroundColor Yellow
    }
    return $problems
}


function Invoke-Install {
    Write-Head "重建环境（幂等，可重复执行）"

    Write-Info "[1/3] 安装 moonshine（editable，不装重依赖）"
    Push-Location "$Root\Moonshine-main\Moonshine-main"
    & $Py -m pip install -e . --no-deps --quiet 2>&1 | Out-Null
    Pop-Location

    Write-Info "[2/3] 安装 marsa（editable）"
    Push-Location $Root
    & $Py -m pip install -e . --no-deps --quiet 2>&1 | Out-Null
    Pop-Location

    Write-Info "[3/3] 把工具/技能/人格装进 Moonshine 运行时"
    & $Py "$Root\ramsey-pack\install.py" --moonshine "$Root\Moonshine-main\Moonshine-main" --home $MHome

    Write-Host ""
    Write-Ok "完成。执行 .\marsa.ps1 doctor 复核。"
}


function Invoke-Run {
    if ([string]::IsNullOrWhiteSpace($Text)) {
        Write-Bad "请给出任务描述。例如："
        Write-Host '  .\marsa.ps1 run "用 ramsey_compare 比较 n=44 上的算子"' -ForegroundColor White
        exit 1
    }

    $proj = $Project
    if ([string]::IsNullOrWhiteSpace($proj)) {
        $proj = "run_" + (Get-Date -Format "MMdd_HHmm")
    }

    Write-Head "启动自主研究"
    Write-Info "项目      : $proj"
    Write-Info "迭代预算  : $Iterations 轮"
    Write-Info "agent 人格: $Agent"
    Write-Info "任务      : $Text"
    Write-Host ""
    Write-Host "（每轮都会写研究日志；Ctrl+C 可随时中断，已完成轮次保留）" -ForegroundColor DarkGray
    Write-Host ""

    Push-Location $Root
    try {
        & $Py -m moonshine --home $MHome ask --mode research --project $proj --agent $Agent --max-iterations $Iterations $Text
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Head "运行结束"
    Write-Info "研究日志: $MHome\projects\$proj\memory\research_log.md"
    Write-Info "看稳定性: .\marsa.ps1 analyze -Project $proj"
}


function Invoke-Ask {
    if ([string]::IsNullOrWhiteSpace($Text)) {
        Write-Bad "请给出问题。"
        exit 1
    }
    Push-Location $Root
    try {
        & $Py -m moonshine --home $MHome ask --mode chat --project general $Text
    } finally {
        Pop-Location
    }
}


function Invoke-Analyze {
    $sessions = Get-ChildItem "$MHome\sessions" -Directory -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending
    if (-not $sessions) { Write-Bad "还没有任何运行记录"; exit 1 }

    $latest = $sessions[0]
    Write-Head "稳定性分析"
    Write-Info "会话: $($latest.Name)"

    $projArg = @()
    if (-not [string]::IsNullOrWhiteSpace($Project)) {
        $projArg = @("$MHome\projects\$Project")
        Write-Info "项目: $Project"
    }

    & $Py "$Root\agent-runs\analyze_session.py" $latest.FullName @projArg
}


function Show-Help {
    $lines = @(
        "",
        "MARSA agent 启动器",
        "==================",
        "",
        "  .\marsa.ps1 doctor            检查环境（跑之前先来一次）",
        "  .\marsa.ps1 install           环境被重置时重建（幂等）",
        "  .\marsa.ps1 run `"<任务>`"       让它自主研究（默认 10 轮）",
        "  .\marsa.ps1 ask `"<问题>`"       单轮问答",
        "  .\marsa.ps1 analyze           分析最近一次运行的稳定性",
        "",
        "可选参数",
        "  -Iterations <n>   自主运行轮数（默认 10）",
        "  -Project <name>   项目名；沿用同名项目可接续之前状态",
        "",
        "示例",
        "  .\marsa.ps1 run `"用 ramsey_compare 比较 n=44 上三个算子，各 3 个 seed、5 秒预算`"",
        "  .\marsa.ps1 run `"继续上一轮，把 Z_2xZ_22 剩余分片跑完`" -Project ramsey_agent_run -Iterations 20",
        ""
    )
    $lines | ForEach-Object { Write-Host $_ -ForegroundColor White }
}


switch ($Command.ToLower()) {
    "doctor"  { Invoke-Doctor | Out-Null }
    "install" { Invoke-Install }
    "run"     { Invoke-Run }
    "ask"     { Invoke-Ask }
    "analyze" { Invoke-Analyze }
    default   { Show-Help }
}
