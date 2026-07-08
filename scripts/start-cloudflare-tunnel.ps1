param(
    [string]$Region = "ap-south-1",
    [string]$InstanceId = "",
    [string]$OriginUrl = "http://127.0.0.1:80"
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Resolve-AwsCommand {
    $cmd = Get-Command aws -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $defaultPath = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
    if (Test-Path $defaultPath) {
        return $defaultPath
    }

    throw "Missing required command: aws"
}

function Invoke-AllowFailure($ScriptBlock) {
    $oldPreference = $ErrorActionPreference
    try {
        $script:ErrorActionPreference = "SilentlyContinue"
        $output = & $ScriptBlock 2>&1
        return @{
            ExitCode = $LASTEXITCODE
            Output = (($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine).Trim()
        }
    } finally {
        $script:ErrorActionPreference = $oldPreference
    }
}

function Require-AwsIdentity {
    $identityCheck = Invoke-AllowFailure { & $Aws sts get-caller-identity --output json }
    if ($identityCheck.ExitCode -ne 0) {
        throw "AWS CLI is not authenticated. Run aws configure first.`n$($identityCheck.Output)"
    }
}

if ([string]::IsNullOrWhiteSpace($InstanceId)) {
    throw "Missing required parameter: InstanceId"
}

$Aws = Resolve-AwsCommand
Require-AwsIdentity

$commands = @(
    "set -euo pipefail",
    "if ! command -v cloudflared >/dev/null 2>&1; then curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared; fi",
    "sudo pkill -f 'cloudflared tunnel --url' || true",
    "nohup sudo cloudflared tunnel --url '$OriginUrl' --no-autoupdate > /var/log/cloudflared.log 2>&1 &",
    "sleep 12",
    "grep -Eo 'https://[-a-zA-Z0-9.]+trycloudflare.com' /var/log/cloudflared.log | tail -n 1 || true",
    "echo ---",
    "tail -n 20 /var/log/cloudflared.log || true"
)

$payload = @{ DocumentName = 'AWS-RunShellScript'; InstanceIds = @($InstanceId); Parameters = @{ commands = $commands } } | ConvertTo-Json -Depth 6 -Compress
$payloadFile = Join-Path $env:TEMP "cloudflared-ssm.json"
Set-Content -Path $payloadFile -Value $payload -Encoding ascii

$commandId = & $Aws ssm send-command --region $Region --cli-input-json file://$payloadFile --query Command.CommandId --output text

for ($i = 0; $i -lt 60; $i++) {
    $invocation = & $Aws ssm get-command-invocation --region $Region --command-id $commandId --instance-id $InstanceId --output json | ConvertFrom-Json
    if ($invocation.Status -eq 'Success') {
        $match = [regex]::Match($invocation.StandardOutputContent, 'https://[-a-zA-Z0-9.]+trycloudflare.com')
        if ($match.Success) {
            Write-Host "Tunnel URL: $($match.Value)"
        } else {
            Write-Host $invocation.StandardOutputContent
        }
        exit 0
    }
    if ($invocation.Status -in @('Cancelled', 'TimedOut', 'Failed')) {
        throw "Cloudflare tunnel command failed:`n$($invocation.StandardErrorContent)`n$($invocation.StandardOutputContent)"
    }
    Start-Sleep -Seconds 5
}

throw "Timed out waiting for the tunnel command to finish."