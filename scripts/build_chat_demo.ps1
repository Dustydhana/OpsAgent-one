$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot "frontend\public\demo-source"
$outputFile = Join-Path $projectRoot "frontend\public\opsagent-chat-demo.mp4"
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source

$inputs = @(
    (Join-Path $sourceRoot "request_msg.png"),
    (Join-Path $sourceRoot "ack_,msg.png"),
    (Join-Path $sourceRoot "approval_msg.png"),
    (Join-Path $sourceRoot "request_completed.png")
)

foreach ($inputFile in $inputs) {
    if (-not (Test-Path -LiteralPath $inputFile)) {
        throw "Missing demo screenshot: $inputFile"
    }
}

$font = "C\:/Windows/Fonts/segoeui.ttf"
$fontBold = "C\:/Windows/Fonts/seguisb.ttf"
$filter = @"
[0:v]scale=1500:650:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xF5F7FA,drawbox=x=140:y=80:w=8:h=112:color=0x4964EE:t=fill,drawtext=fontfile='$fontBold':text='Request received':fontcolor=0x16191F:fontsize=54:x=180:y=82,drawtext=fontfile='$font':text='An operator asks OpsAgent to stop an exact infrastructure resource.':fontcolor=0x596472:fontsize=27:x=180:y=148,drawtext=fontfile='$fontBold':text='01 / 04':fontcolor=0x4964EE:fontsize=24:x=w-tw-150:y=105,drawtext=fontfile='$fontBold':text='A2Z OPSAGENT  |  GUARDED CHAT OPERATIONS':fontcolor=0x6A7480:fontsize=20:x=150:y=h-72,fade=t=in:st=0:d=0.35,fade=t=out:st=3.65:d=0.35,setpts=PTS-STARTPTS[v0];
[1:v]scale=1500:650:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xF5F7FA,drawbox=x=140:y=80:w=8:h=112:color=0x4964EE:t=fill,drawtext=fontfile='$fontBold':text='Acknowledged safely':fontcolor=0x16191F:fontsize=54:x=180:y=82,drawtext=fontfile='$font':text='The agent resolves the target and creates a time-limited approval request. No change has run.':fontcolor=0x596472:fontsize=27:x=180:y=148,drawtext=fontfile='$fontBold':text='02 / 04':fontcolor=0x4964EE:fontsize=24:x=w-tw-150:y=105,drawtext=fontfile='$fontBold':text='A2Z OPSAGENT  |  GUARDED CHAT OPERATIONS':fontcolor=0x6A7480:fontsize=20:x=150:y=h-72,fade=t=in:st=0:d=0.35,fade=t=out:st=3.65:d=0.35,setpts=PTS-STARTPTS[v1];
[2:v]scale=1500:650:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xF5F7FA,drawbox=x=140:y=80:w=8:h=112:color=0x4964EE:t=fill,drawtext=fontfile='$fontBold':text='Explicit approval':fontcolor=0x16191F:fontsize=54:x=180:y=82,drawtext=fontfile='$font':text='An authorized user approves the exact request ID before execution.':fontcolor=0x596472:fontsize=27:x=180:y=148,drawtext=fontfile='$fontBold':text='03 / 04':fontcolor=0x4964EE:fontsize=24:x=w-tw-150:y=105,drawtext=fontfile='$fontBold':text='A2Z OPSAGENT  |  GUARDED CHAT OPERATIONS':fontcolor=0x6A7480:fontsize=20:x=150:y=h-72,fade=t=in:st=0:d=0.35,fade=t=out:st=3.65:d=0.35,setpts=PTS-STARTPTS[v2];
[3:v]scale=1500:650:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xF5F7FA,drawbox=x=140:y=80:w=8:h=112:color=0x28A36A:t=fill,drawtext=fontfile='$fontBold':text='Executed and verified':fontcolor=0x16191F:fontsize=54:x=180:y=82,drawtext=fontfile='$font':text='AWS confirms the final state and OpsAgent records the complete audit evidence.':fontcolor=0x596472:fontsize=27:x=180:y=148,drawtext=fontfile='$fontBold':text='04 / 04':fontcolor=0x28A36A:fontsize=24:x=w-tw-150:y=105,drawtext=fontfile='$fontBold':text='A2Z OPSAGENT  |  GUARDED CHAT OPERATIONS':fontcolor=0x6A7480:fontsize=20:x=150:y=h-72,fade=t=in:st=0:d=0.35,fade=t=out:st=3.65:d=0.35,setpts=PTS-STARTPTS[v3];
[v0][v1][v2][v3]concat=n=4:v=1:a=0:unsafe=1,setsar=1,format=yuv420p[outv]
"@

$arguments = @("-y")
foreach ($inputFile in $inputs) {
    $arguments += @("-loop", "1", "-t", "4", "-framerate", "30", "-i", $inputFile)
}
$arguments += @(
    "-filter_complex", $filter,
    "-map", "[outv]",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "19",
    "-movflags", "+faststart",
    "-an",
    $outputFile
)

& $ffmpeg @arguments
if ($LASTEXITCODE -ne 0) {
    throw "FFmpeg failed with exit code $LASTEXITCODE"
}

Write-Output $outputFile
