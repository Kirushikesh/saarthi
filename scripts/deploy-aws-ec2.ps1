param(
    [string]$Region = "ap-south-1",
    [string]$RepositoryName = "saarthi",
    [string]$InstanceName = "saarthi-hackathon-ec2",
    [string]$InstanceType = "t3.small",
    [string]$ImageTag = "latest",
    [string]$EnvFile = "backend/.env",
    [string]$InstanceId = "",
    [string]$AccessRoleName = "SaarthiEc2EcrRole",
    [string]$InstanceProfileName = "SaarthiEc2InstanceProfile",
    [string]$SecurityGroupName = "saarthi-ec2-sg",
    [string]$AmiParameter = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64"
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

function ConvertTo-Base64Text([string]$Text) {
    return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
}

function New-TempFilePath([string]$FileName) {
    $tempRoot = $env:TEMP
    if ([string]::IsNullOrWhiteSpace($tempRoot)) {
        $tempRoot = $env:TMPDIR
    }
    if ([string]::IsNullOrWhiteSpace($tempRoot)) {
        $tempRoot = [System.IO.Path]::GetTempPath()
    }

    return Join-Path $tempRoot $FileName
}

function New-RuntimeEnvContent {
    $openAiKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY")
    $googleKey = [Environment]::GetEnvironmentVariable("GOOGLE_API_KEY")
    $llmModel = [Environment]::GetEnvironmentVariable("LLM_MODEL")
    $liveModel = [Environment]::GetEnvironmentVariable("LIVE_MODEL")

    if ([string]::IsNullOrWhiteSpace($llmModel)) {
        $llmModel = "google_genai:gemini-2.5-flash"
    }
    if ([string]::IsNullOrWhiteSpace($liveModel)) {
        $liveModel = "gemini-3.1-flash-live-preview"
    }

    $lines = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($openAiKey)) {
        $lines.Add("OPENAI_API_KEY=$openAiKey")
    }
    if (-not [string]::IsNullOrWhiteSpace($googleKey)) {
        $lines.Add("GOOGLE_API_KEY=$googleKey")
    }
    $lines.Add("LLM_MODEL=$llmModel")
    $lines.Add("LIVE_MODEL=$liveModel")
    $lines.Add("PORT=8000")
    return ($lines -join "`n")
}

function Get-AwsTextValue([scriptblock]$Command) {
    $check = Invoke-AllowFailure $Command
    if ($check.ExitCode -ne 0) {
        throw $check.Output
    }

    return [string]$check.Output
}

function Send-RemoteCommands([string]$TargetInstanceId, [string[]]$Commands) {
    $payload = @{
        DocumentName = 'AWS-RunShellScript'
        InstanceIds = @($TargetInstanceId)
        Parameters = @{ commands = $Commands }
    } | ConvertTo-Json -Depth 6 -Compress

    $payloadFile = New-TempFilePath "saarthi-ssm-command.json"
    Set-Content -Path $payloadFile -Value $payload -Encoding ascii
    $commandId = & $Aws ssm send-command --region $Region --cli-input-json file://$payloadFile --query Command.CommandId --output text

    for ($i = 0; $i -lt 60; $i++) {
        $invocation = & $Aws ssm get-command-invocation --region $Region --command-id $commandId --instance-id $TargetInstanceId --output json | ConvertFrom-Json
        if ($invocation.Status -in @('Success', 'Cancelled', 'TimedOut', 'Failed', 'Cancelled')) {
            if ($invocation.Status -ne 'Success') {
                throw "Remote update failed: $($invocation.StandardErrorContent)`n$($invocation.StandardOutputContent)"
            }
            return $invocation
        }
        Start-Sleep -Seconds 5
    }

    throw "Timed out waiting for SSM command $commandId on instance $TargetInstanceId."
}

$Aws = Resolve-AwsCommand
Require-Command docker
Require-AwsIdentity
Load-EnvFile $EnvFile

Write-Host "Using AWS region: $Region"
$AccountId = Get-AwsTextValue { & $Aws sts get-caller-identity --query Account --output text }
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$ImageReference = $RepositoryName + ":" + $ImageTag
$ImageUri = "$Registry/$ImageReference"

Write-Host "Ensuring ECR repository exists: $RepositoryName"
$EcrCheck = Invoke-AllowFailure { & $Aws ecr describe-repositories --repository-names $RepositoryName --region $Region }
if ($EcrCheck.ExitCode -ne 0) {
    & $Aws ecr create-repository --repository-name $RepositoryName --region $Region *> $null
}

Write-Host "Logging Docker into ECR"
& $Aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $Registry

Write-Host "Building Docker image"
docker build -t $ImageReference .

Write-Host "Pushing Docker image: $ImageUri"
docker tag $ImageReference $ImageUri
docker push $ImageUri

$RuntimeEnvB64 = ConvertTo-Base64Text (New-RuntimeEnvContent)

if (-not [string]::IsNullOrWhiteSpace($InstanceId)) {
    Write-Host "Updating existing EC2 instance: $InstanceId"
    $remoteCommands = @(
        "set -euo pipefail",
        "echo '$RuntimeEnvB64' | base64 -d | sudo tee /opt/saarthi.env >/dev/null",
        "aws ecr get-login-password --region $Region | sudo docker login --username AWS --password-stdin $Registry",
        "sudo docker pull $ImageUri",
        "sudo docker rm -f saarthi-demo || true",
        "sudo docker run -d --restart unless-stopped --name saarthi-demo --env-file /opt/saarthi.env -p 80:8000 $ImageUri",
        "sudo docker ps --filter name=saarthi-demo --format '{{.Names}}|{{.Status}}|{{.Ports}}'"
    )
    $updateResult = Send-RemoteCommands -TargetInstanceId $InstanceId -Commands $remoteCommands
    Write-Host $updateResult.StandardOutputContent
    $PublicIp = [string](& $Aws ec2 describe-instances --region $Region --instance-ids $InstanceId --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
    if ([string]::IsNullOrWhiteSpace($PublicIp) -or $PublicIp -eq "None") {
        throw "Updated instance $InstanceId but could not resolve public IP."
    }
    Write-Host ""
    Write-Host "Deployment finished."
    Write-Host "URL: http://$PublicIp"
    Write-Host "Health: http://$PublicIp/api/health"
    exit 0
}

$RoleTrustFile = New-TempFilePath "saarthi-ec2-trust-policy.json"
@"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@ | Set-Content -Path $RoleTrustFile -Encoding ascii

Write-Host "Ensuring EC2 IAM role exists: $AccessRoleName"
$RoleCheck = Invoke-AllowFailure { & $Aws iam get-role --role-name $AccessRoleName --query Role.Arn --output text }
$RoleArn = if ($RoleCheck.ExitCode -eq 0) { [string]$RoleCheck.Output } else { "" }
if ([string]::IsNullOrWhiteSpace($RoleArn)) {
    $RoleArn = & $Aws iam create-role `
        --role-name $AccessRoleName `
        --assume-role-policy-document "file://$RoleTrustFile" `
        --query Role.Arn `
        --output text
    & $Aws iam attach-role-policy --role-name $AccessRoleName --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
    & $Aws iam attach-role-policy --role-name $AccessRoleName --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
    Start-Sleep -Seconds 10
}

Write-Host "Ensuring instance profile exists: $InstanceProfileName"
$ProfileCheck = Invoke-AllowFailure { & $Aws iam get-instance-profile --instance-profile-name $InstanceProfileName --query InstanceProfile.Arn --output text }
if ($ProfileCheck.ExitCode -ne 0) {
    & $Aws iam create-instance-profile --instance-profile-name $InstanceProfileName *> $null
    Start-Sleep -Seconds 5
}

$ProfileRoleCheck = Invoke-AllowFailure { & $Aws iam add-role-to-instance-profile --instance-profile-name $InstanceProfileName --role-name $AccessRoleName }
if ($ProfileRoleCheck.ExitCode -ne 0 -and $ProfileRoleCheck.Output -notmatch "LimitExceeded|EntityAlreadyExists") {
    throw "Could not attach role to instance profile. AWS said: $($ProfileRoleCheck.Output)"
}

$VpcId = Get-AwsTextValue { & $Aws ec2 describe-vpcs --region $Region --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text }
if ([string]::IsNullOrWhiteSpace($VpcId) -or $VpcId -eq "None") {
    throw "No default VPC found in region $Region. Create a default VPC or set up a subnet manually."
}

$SubnetId = Get-AwsTextValue { & $Aws ec2 describe-subnets --region $Region --filters Name=vpc-id,Values=$VpcId --query "Subnets[0].SubnetId" --output text }

$SecurityGroupId = Get-AwsTextValue {
    & $Aws ec2 describe-security-groups --region $Region `
        --filters Name=vpc-id,Values=$VpcId Name=group-name,Values=$SecurityGroupName `
        --query "SecurityGroups[0].GroupId" --output text
}
if ([string]::IsNullOrWhiteSpace($SecurityGroupId) -or $SecurityGroupId -eq "None") {
    $SecurityGroupId = Get-AwsTextValue {
        & $Aws ec2 create-security-group --region $Region `
            --group-name $SecurityGroupName `
            --description "Saarthi EC2 demo security group" `
            --vpc-id $VpcId `
            --query GroupId --output text
    }
    & $Aws ec2 authorize-security-group-ingress --region $Region --group-id $SecurityGroupId --protocol tcp --port 80 --cidr 0.0.0.0/0 *> $null
}

$AmiId = Get-AwsTextValue { & $Aws ssm get-parameter --region $Region --name $AmiParameter --query Parameter.Value --output text }

$UserDataTemplate = @'
#!/bin/bash
set -euo pipefail

dnf update -y
dnf install -y docker awscli
systemctl enable --now docker

cat >/opt/saarthi.env.b64 <<'EOF'
__ENV_B64__
EOF
base64 -d /opt/saarthi.env.b64 >/opt/saarthi.env
rm -f /opt/saarthi.env.b64

aws ecr get-login-password --region __REGION__ | docker login --username AWS --password-stdin __REGISTRY__
docker rm -f saarthi-demo || true
docker run -d --restart unless-stopped --name saarthi-demo --env-file /opt/saarthi.env -p 80:8000 __IMAGE_URI__
'@

$UserData = $UserDataTemplate.Replace("__ENV_B64__", $RuntimeEnvB64).Replace("__REGION__", $Region).Replace("__REGISTRY__", $Registry).Replace("__IMAGE_URI__", $ImageUri)
$UserDataFile = New-TempFilePath "saarthi-ec2-user-data.sh"
Set-Content -Path $UserDataFile -Value $UserData -Encoding ascii

Write-Host "Launching EC2 instance: $InstanceName"
$LaunchJson = & $Aws ec2 run-instances `
    --region $Region `
    --image-id $AmiId `
    --instance-type $InstanceType `
    --iam-instance-profile Name=$InstanceProfileName `
    --security-group-ids $SecurityGroupId `
    --subnet-id $SubnetId `
    --associate-public-ip-address `
    --user-data file://$UserDataFile `
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$InstanceName}]" `
    --query "Instances[0].[InstanceId,PublicIpAddress]" `
    --output json | ConvertFrom-Json

$InstanceId = [string]$LaunchJson[0]
if ([string]::IsNullOrWhiteSpace($InstanceId)) {
    throw "AWS did not return an instance id."
}

Write-Host "Waiting for instance to enter running state"
& $Aws ec2 wait instance-running --region $Region --instance-ids $InstanceId

Write-Host "Waiting for public IP address"
$PublicIp = ""
for ($i = 0; $i -lt 30; $i++) {
    $PublicIp = [string](& $Aws ec2 describe-instances --region $Region --instance-ids $InstanceId --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
    if (-not [string]::IsNullOrWhiteSpace($PublicIp) -and $PublicIp -ne "None") {
        break
    }
    Start-Sleep -Seconds 10
}

if ([string]::IsNullOrWhiteSpace($PublicIp) -or $PublicIp -eq "None") {
    throw "Instance is running, but no public IP was assigned."
}

Write-Host "Waiting for the app to become healthy"
$HealthUrl = "http://$PublicIp/api/health"
for ($i = 0; $i -lt 90; $i++) {
    try {
        $healthCheck = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 $HealthUrl
        if ($healthCheck.StatusCode -ge 200 -and $healthCheck.StatusCode -lt 300) {
            Write-Host "Health response: $($healthCheck.Content)"
            break
        }
    } catch {
        Write-Host "Health check not ready yet ($($i + 1)/90): $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 10
}

if ($i -ge 90) {
    throw "App did not become healthy at $HealthUrl after waiting. Check the instance user-data and container logs."
}

Write-Host ""
Write-Host "Deployment finished."
Write-Host "URL: http://$PublicIp"
Write-Host "Health: $HealthUrl"
