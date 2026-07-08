# Docker Run Guide

Build the full-stack image from the repo root:

```powershell
docker build -t saarthi-fullstack:local .
```

Run the app:

```powershell
docker run -d --name saarthi-fullstack-local -p 8000:8000 --env-file backend/.env saarthi-fullstack:local
```

Open the app:

```text
http://localhost:8000
```

Check backend health:

```powershell
curl http://localhost:8000/api/health
```

View logs:

```powershell
docker logs -f saarthi-fullstack-local
```

Stop and remove the container:

```powershell
docker rm -f saarthi-fullstack-local
```

If the container name already exists, remove it first and rerun the `docker run`
command:

```powershell
docker rm -f saarthi-fullstack-local
```
