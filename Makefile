SHELL := powershell.exe
.SHELLFLAGS := -NoProfile -ExecutionPolicy Bypass -Command

REGION ?= ap-south-1
ENV_FILE ?= backend/.env
INSTANCE_ID ?= i-013b16ea0f8a47559
ORIGIN_URL ?= http://127.0.0.1:80

.PHONY: help ec2-deploy ec2-update cloudflare-tunnel

help:
	@$targets = @(
		[pscustomobject]@{ Target = 'ec2-deploy'; Description = 'Fresh deploy to EC2 (build, push, launch)' },
		[pscustomobject]@{ Target = 'ec2-update'; Description = 'Update the running EC2 instance in place' },
		[pscustomobject]@{ Target = 'cloudflare-tunnel'; Description = 'Start free HTTPS demo tunnel via Cloudflare' }
	); $targets | Format-Table -AutoSize; `
	Write-Host "Variables:"; `
	Write-Host "  REGION=$(REGION)"; `
	Write-Host "  ENV_FILE=$(ENV_FILE)"; `
	Write-Host "  INSTANCE_ID=$(INSTANCE_ID)"; `
	Write-Host "  ORIGIN_URL=$(ORIGIN_URL)"

ec2-deploy:
	& '.\scripts\deploy-aws-ec2.ps1' -Region $(REGION) -EnvFile '$(ENV_FILE)'

ec2-update:
	& '.\scripts\deploy-aws-ec2.ps1' -Region $(REGION) -EnvFile '$(ENV_FILE)' -InstanceId $(INSTANCE_ID)

cloudflare-tunnel:
	& '.\scripts\start-cloudflare-tunnel.ps1' -Region $(REGION) -InstanceId $(INSTANCE_ID) -OriginUrl '$(ORIGIN_URL)'