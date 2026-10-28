# .\Monitor-ProcessEnd.ps1 -ProcessName notepad
# .\Monitor-ProcessByPid.ps1 -ProcessId 12345
# Get-NetTCPConnection -State Established | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State, OwningProcess, @{Name="ProcessName";Expression={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}} | Format-Table -AutoSize
# Get-NetTCPConnection | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State, OwningProcess, @{Name="ProcessName";Expression={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}} | Format-Table -AutoSize

param(
    [Parameter(ParameterSetName='ByName', Mandatory=$true)]
    [String]$ProcessName,

    [Parameter(ParameterSetName='ById', Mandatory=$true)]
    [Int]$ProcessId
)

# =================================================================
# 🚨🚨🚨 [필수 설정: 이 부분을 사용자 환경에 맞게 수정하세요] 🚨🚨🚨
# =================================================================

# 1. SMTP 서버 정보 (예: Gmail 설정)
$SMTPServer = "smtp.gmail.com" # 네이버: smtp.naver.com, Outlook/Hotmail: smtp.office365.com
$SMTPPort = 587
$UseSSL = $true

# 2. 이메일 계정 정보 (발신자)
$SenderEmail = "your_sender_email@gmail.com"
$CredentialUser = "your_sender_username" # 보통 SenderEmail과 동일

# 3. 비밀번호 (보안 경고: 반드시 앱 비밀번호를 사용하세요!)
$CredentialPassword = "your_app_password_here"

# 4. 수신자 정보
$RecipientEmail = "your_recipient_email@example.com"

# =================================================================

$CheckIntervalSeconds = 5 
$ProcessToMonitor = $null

# ----------------- 1. 프로세스 검색 -----------------
if ($PSCmdlet.ParameterSetName -eq 'ByName') {
    $SearchName = $ProcessName -replace '\.exe$', ''
    $ProcessToMonitor = Get-Process -Name "$SearchName" -ErrorAction SilentlyContinue
    $MonitorTarget = "이름: $SearchName"
} elseif ($PSCmdlet.ParameterSetName -eq 'ById') {
    $ProcessToMonitor = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $MonitorTarget = "PID: $ProcessId"
}

# ----------------- 2. 초기 프로세스 존재 여부 확인 -----------------
if (-not $ProcessToMonitor) {
    Write-Host "❌ [$MonitorTarget]에 해당하는 프로세스가 현재 실행 중이지 않습니다. 스크립트 종료." -ForegroundColor Red
    exit
}

$FinalName = $ProcessToMonitor.Name
$FinalId = $ProcessToMonitor.Id

Write-Host "➡️ [$MonitorTarget] 모니터링 시작..." -ForegroundColor Yellow
Write-Host "✅ [$FinalName] (PID: $FinalId) 프로세스 실행 중. 종료를 확인하는 중..." -ForegroundColor Green

# ----------------- 3. 핵심 모니터링 루프 -----------------
while (Get-Process -Id $FinalId -ErrorAction SilentlyContinue) {
    Write-Host "⏳ [$FinalName] (PID: $FinalId) 실행 중... ($CheckIntervalSeconds 초 후 재확인)"
    Start-Sleep -Seconds $CheckIntervalSeconds
}

# ----------------- 4. 프로세스 종료 알림 및 이메일 전송 -----------------

# 알림 내용 구성
$TerminationTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$EmailSubject = "✅ 프로세스 종료 알림: [$FinalName] (PID: $FinalId)"
$EmailBody = @"
모니터링 대상이었던 프로세스가 종료되었습니다.

- 프로세스 이름: $FinalName
- PID: $FinalId
- 종료 확인 시각: $TerminationTime
- 모니터링 방식: $MonitorTarget
"@

Write-Host ""
Write-Host "🔔 [$FinalName] 프로세스가 종료되었습니다. 이메일 전송 시작..." -ForegroundColor Black -BackgroundColor Cyan

try {
    # 보안 문자열로 비밀번호 변환
    $SecurePassword = ConvertTo-SecureString $CredentialPassword -AsPlainText -Force
    $Credential = New-Object System.Management.Automation.PSCredential($CredentialUser, $SecurePassword)

    # 이메일 전송
    Send-MailMessage `
        -From $SenderEmail `
        -To $RecipientEmail `
        -Subject $EmailSubject `
        -Body $EmailBody `
        -SmtpServer $SMTPServer `
        -Port $SMTPPort `
        -Credential $Credential `
        -UseSsl $UseSSL `
        -BodyAsHtml:$false

    Write-Host "✅ 이메일 알림이 성공적으로 전송되었습니다." -ForegroundColor Green
}
catch {
    Write-Host "❌ 이메일 전송 실패: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "설정(SMTP 서버, 포트, 인증 정보)을 다시 확인해 주세요." -ForegroundColor Red
}

Write-Host "스크립트 종료."