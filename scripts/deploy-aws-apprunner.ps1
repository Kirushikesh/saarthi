param(
    [string]$Region = "ap-south-1",
    [string]$RepositoryName = "saarthi",
    [string]$ServiceName = "saarthi-hackathon",
    [string]$ImageTag = "latest",
    [string]$AccessRoleName = "AppRunnerECRAccessRole",
    [string]$EnvFile = "backend/.env"
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
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

function Require-AwsIdentity {
    $identityCheck = Invoke-AllowFailure { & $Aws sts get-caller-identity --output json }
    if ($identityCheck.ExitCode -ne 0) {
        throw @"
AWS CLI is installed, but it is not authenticated.

Fix it with one of these options:
  aws configure
  [Environment]::SetEnvironmentVariable('AWS_ACCESS_KEY_ID', '...')
  [Environment]::SetEnvironmentVariable('AWS_SECRET_ACCESS_KEY', '...')
  [Environment]::SetEnvironmentVariable('AWS_SESSION_TOKEN', '...')  # only for temporary creds

Then re-run the script.

AWS said:
$($identityCheck.Output)
"@
    }
}

function Require-Env($Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing environment variable: $Name"
    }
    return $value
}

function Load-EnvFile($Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        if ($line -match '^(?<key>[A-Za-z_][A-Za-z0-9_]*)=(?<value>.*)$') {
            $value = $matches.value.Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($matches.key, $value)
        }
    }
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

$Aws = Resolve-AwsCommand
Require-Command docker
Require-AwsIdentity
Load-EnvFile $EnvFile

$OpenAiKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY")
$GoogleKey = [Environment]::GetEnvironmentVariable("GOOGLE_API_KEY")
$LlmModel = [Environment]::GetEnvironmentVariable("LLM_MODEL")
$LiveModel = [Environment]::GetEnvironmentVariable("LIVE_MODEL")

if ([string]::IsNullOrWhiteSpace($LlmModel)) {
    $LlmModel = "google_genai:gemini-2.5-flash"
}
if ([string]::IsNullOrWhiteSpace($LiveModel)) {
    $LiveModel = "gemini-3.1-flash-live-preview"
}

Write-Host "Using AWS region: $Region"
$AccountId = & $Aws sts get-caller-identity --query Account --output text
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$ImageUri = "$Registry/$RepositoryName`:$ImageTag"

Write-Host "Ensuring ECR repository exists: $RepositoryName"
$EcrCheck = Invoke-AllowFailure { & $Aws ecr describe-repositories --repository-names $RepositoryName --region $Region }
if ($EcrCheck.ExitCode -ne 0) {
    & $Aws ecr create-repository --repository-name $RepositoryName --region $Region *> $null
}

Write-Host "Logging Docker into ECR"
& $Aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $Registry

Write-Host "Building Docker image"
docker build -t "$RepositoryName`:$ImageTag" .

Write-Host "Pushing Docker image: $ImageUri"
docker tag "$RepositoryName`:$ImageTag" $ImageUri
docker push $ImageUri

$TrustPolicyFile = Join-Path $env:TEMP "apprunner-ecr-trust-policy.json"
@"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "build.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@ | Set-Content -Path $TrustPolicyFile -Encoding ascii

Write-Host "Ensuring App Runner ECR access role exists: $AccessRoleName"
$RoleCheck = Invoke-AllowFailure { & $Aws iam get-role --role-name $AccessRoleName --query Role.Arn --output text }
$AccessRoleArn = if ($RoleCheck.ExitCode -eq 0) { [string]$RoleCheck.Output } else { "" }
if ($RoleCheck.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($AccessRoleArn)) {
    $AccessRoleArn = & $Aws iam create-role `
        --role-name $AccessRoleName `
        --assume-role-policy-document "file://$TrustPolicyFile" `
        --query Role.Arn `
        --output text
    & $Aws iam attach-role-policy `
        --role-name $AccessRoleName `
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
    Start-Sleep -Seconds 10
}

$RuntimeVars = [ordered]@{
    OPENAI_API_KEY = $OpenAiKey
    LLM_MODEL = $LlmModel
    LIVE_MODEL = $LiveModel
    PORT = "8000"
}

if (-not [string]::IsNullOrWhiteSpace($GoogleKey)) {
    $RuntimeVars.GOOGLE_API_KEY = $GoogleKey
}

$RuntimeVarsJson = ($RuntimeVars | ConvertTo-Json -Compress)
$SourceConfigFile = Join-Path $env:TEMP "saarthi-apprunner-source-config.json"
@"
{
  "AuthenticationConfiguration": {
    "AccessRoleArn": "$AccessRoleArn"
  },
  "AutoDeploymentsEnabled": false,
  "ImageRepository": {
    "ImageIdentifier": "$ImageUri",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {
      "Port": "8000",
      "RuntimeEnvironmentVariables": $RuntimeVarsJson
    }
  }
}
"@ | Set-Content -Path $SourceConfigFile -Encoding ascii

$HealthConfigFile = Join-Path $env:TEMP "saarthi-apprunner-health-config.json"
@"
{
  "Protocol": "HTTP",
  "Path": "/api/health",
  "Interval": 10,
  "Timeout": 5,
  "HealthyThreshold": 1,
  "UnhealthyThreshold": 5
}
"@ | Set-Content -Path $HealthConfigFile -Encoding ascii

Write-Host "Checking for existing App Runner service: $ServiceName"
$ListCheck = Invoke-AllowFailure {
    & $Aws apprunner list-services `
        --region $Region `
        --query "ServiceSummaryList[?ServiceName=='$ServiceName'].ServiceArn | [0]" `
        --output text
}
if ($ListCheck.ExitCode -ne 0) {
    throw "Could not list App Runner services. AWS said: $($ListCheck.Output)"
}
$ServiceArn = [string]$ListCheck.Output

if ($ServiceArn -and $ServiceArn -ne "None") {
    Write-Host "Updating App Runner service"
    & $Aws apprunner update-service `
        --region $Region `
        --service-arn $ServiceArn `
        --source-configuration "file://$SourceConfigFile" `
        --health-check-configuration "file://$HealthConfigFile" *> $null
} else {
    Write-Host "Creating App Runner service"
    $CreateCheck = Invoke-AllowFailure {
        & $Aws apprunner create-service `
            --region $Region `
            --service-name $ServiceName `
            --source-configuration "file://$SourceConfigFile" `
            --health-check-configuration "file://$HealthConfigFile" `
            --query Service.ServiceArn `
            --output text
    }
    if ($CreateCheck.ExitCode -ne 0) {
        throw "Could not create App Runner service. AWS said: $($CreateCheck.Output)"
    }
    $ServiceArn = [string]$CreateCheck.Output
}

Write-Host "Waiting for App Runner service to become RUNNING"
do {
    Start-Sleep -Seconds 20
    $ServiceJson = & $Aws apprunner describe-service --region $Region --service-arn $ServiceArn | ConvertFrom-Json
    $Status = $ServiceJson.Service.Status
    Write-Host "Status: $Status"
} while ($Status -eq "CREATE_IN_PROGRESS" -or $Status -eq "OPERATION_IN_PROGRESS")

$ServiceUrl = $ServiceJson.Service.ServiceUrl
Write-Host ""
Write-Host "Deployment finished."
Write-Host "URL: https://$ServiceUrl"
Write-Host "Health: https://$ServiceUrl/api/health"
