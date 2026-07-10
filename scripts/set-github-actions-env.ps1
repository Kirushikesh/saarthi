param(
    [string]$EnvFile = ".env",
    [string]$Repository = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Read-DotEnv($Path) {
    if (-not (Test-Path $Path)) {
        throw "Env file not found: $Path"
    }

    $values = [ordered]@{}
    Get-Content -Path $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        if ($line -match '^(?<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<value>.*)$') {
            $value = $matches.value.Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $values[$matches.key] = $value
        }
    }

    return $values
}

function Set-GitHubSecret($Name, $Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Write-Host "Skipping empty secret: $Name"
        return
    }

    if ($DryRun) {
        Write-Host "Would set GitHub secret: $Name"
        return
    }

    if ([string]::IsNullOrWhiteSpace($Repository)) {
        $Value | gh secret set $Name
    } else {
        $Value | gh secret set $Name --repo $Repository
    }
    Write-Host "Set GitHub secret: $Name"
}

function Set-GitHubVariable($Name, $Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Write-Host "Skipping empty variable: $Name"
        return
    }

    if ($DryRun) {
        Write-Host "Would set GitHub variable: $Name=$Value"
        return
    }

    if ([string]::IsNullOrWhiteSpace($Repository)) {
        gh variable set $Name --body $Value
    } else {
        gh variable set $Name --body $Value --repo $Repository
    }
    Write-Host "Set GitHub variable: $Name"
}

Require-Command gh

$envValues = Read-DotEnv $EnvFile

$secretNames = @(
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "EC2_INSTANCE_ID",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY"
)

$variableNames = @(
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "ECR_REPOSITORY",
    "LLM_MODEL",
    "LIVE_MODEL"
)

foreach ($name in $secretNames) {
    if ($envValues.Contains($name)) {
        Set-GitHubSecret -Name $name -Value $envValues[$name]
    }
}

foreach ($name in $variableNames) {
    if ($envValues.Contains($name)) {
        $targetName = if ($name -eq "AWS_DEFAULT_REGION") { "AWS_REGION" } else { $name }
        Set-GitHubVariable -Name $targetName -Value $envValues[$name]
    }
}

if (-not $envValues.Contains("EC2_INSTANCE_ID")) {
    Write-Warning "EC2_INSTANCE_ID is not present in $EnvFile. Add it before running deployment workflow."
}

if (-not $envValues.Contains("AWS_REGION") -and -not $envValues.Contains("AWS_DEFAULT_REGION")) {
    Write-Warning "AWS_REGION is not present in $EnvFile. The workflow will default to ap-south-1."
}

Write-Host "Done."
