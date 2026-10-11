$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot "frontend\public\demo-source"
$generatedRoot = Join-Path $projectRoot "frontend\public\demo-generated"
$publicRoot = Join-Path $projectRoot "frontend\public"
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
New-Item -ItemType Directory -Force -Path $generatedRoot | Out-Null

function Invoke-FFmpeg([string[]]$Arguments) {
    & $ffmpeg @Arguments
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg failed with exit code $LASTEXITCODE" }
}

function New-ContinuousDemo {
    param(
        [string]$Name,
        [string]$Title,
        [string[]]$Files,
        [string[]]$InputFilters,
        [int]$Duration = 18
    )
    $still = Join-Path $generatedRoot "$Name-thread.png"
    $output = Join-Path $publicRoot "opsagent-$Name-demo.mp4"
    $fontBold = "C\:/Windows/Fonts/seguisb.ttf"
    $args = @("-y")
    foreach ($file in $Files) { $args += @("-i", (Join-Path $sourceRoot $file)) }
    $parts = @()
    for ($index = 0; $index -lt $Files.Count; $index++) {
        $privacy = if ($InputFilters[$index]) { $InputFilters[$index] + "," } else { "" }
        $parts += "[$index`:v]${privacy}scale=1400:-2,pad=1400:ih+42:0:0:color=white,setsar=1[s$index]"
    }
    $labels = (0..($Files.Count - 1) | ForEach-Object { "[s$_]" }) -join ""
    $parts += "${labels}vstack=inputs=$($Files.Count),pad=1920:ih+260:(ow-iw)/2:170:color=0xF5F7FA,drawbox=x=0:y=0:w=iw:h=112:color=white:t=fill,drawtext=fontfile='$fontBold':text='$Title':fontcolor=0x18202A:fontsize=34:x=260:y=38,drawtext=fontfile='$fontBold':text='A2Z OPSAGENT':fontcolor=0x4964EE:fontsize=20:x=70:y=45[out]"
    $args += @("-filter_complex", ($parts -join ";"), "-map", "[out]", "-frames:v", "1", "-update", "1", $still)
    Invoke-FFmpeg $args

    $probe = & ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 $still
    $height = [int]$probe
    $travel = [Math]::Max(0, $height - 1080)
    $videoFilter = "crop=1920:1080:0:'$travel*t/$Duration',fps=30,format=yuv420p"
    Invoke-FFmpeg @("-y", "-loop", "1", "-framerate", "30", "-i", $still, "-t", "$Duration", "-vf", $videoFilter, "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-movflags", "+faststart", "-an", $output)
}

New-ContinuousDemo -Name "chat" -Title "Guarded operation from OpsAgent Chat" -Duration 16 -Files @(
    "request_msg.png", "ack_,msg.png", "approval_msg.png", "request_completed.png"
) -InputFilters @("", "", "", "")

New-ContinuousDemo -Name "slack" -Title "Autonomous incident investigation in Slack" -Duration 15 -Files @(
    "Slack_grafnaa_tiggerd .png", "slack_grafana_ack_connecinting to sever.png", "slack_granfana_analyze.png"
) -InputFilters @(
    "", "", "drawbox=x=440:y=61:w=400:h=26:color=white:t=fill"
)

New-ContinuousDemo -Name "gmail" -Title "Approval-controlled AWS operation from Gmail" -Duration 24 -Files @(
    "Gmail_request.png", "gmail_which_vm_need_start.png", "Gmail_user_reply_confrimation.png",
    "gmail_agent_ack_request.png", "Gmail_Authorized approver.png", "gmail_result.png"
) -InputFilters @(
    "drawbox=x=205:y=76:w=280:h=50:color=white:t=fill",
    "drawbox=x=48:y=16:w=310:h=44:color=white:t=fill",
    "",
    "drawbox=x=50:y=15:w=290:h=42:color=white:t=fill,drawbox=x=105:y=116:w=250:h=18:color=white:t=fill",
    "",
    "drawbox=x=75:y=27:w=360:h=50:color=white:t=fill,drawbox=x=155:y=142:w=390:h=82:color=white:t=fill"
)

Write-Output "Continuous demo videos created in $publicRoot"
