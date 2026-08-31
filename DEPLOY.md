# Deploying TracePulse to an Oracle Cloud VM (Docker Compose)

Manual deploys — no CI/CD. Everything below assumes Ubuntu on an Oracle VM
with Docker + Docker Compose plugin installed and port 22 open.

## Architecture

```
Internet :80/:443 -> caddy (static frontend + /api proxy) -> api :8000 -> db (internal only)
```

- `docker-compose.prod.yml` — prod stack, `restart: always` on all services, fixed ports.
- `frontend/Dockerfile.prod` — builds the Vite SPA and serves it with Caddy.
  The frontend is served **same-origin** and calls the API at `/api`
  (Caddy strips the prefix), so no CORS and no Vite dev server in prod.
- db has **no host port binding** — it's only reachable on the compose network.

## One-time VM setup

```bash
# install docker (official convenience script)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # then log out & back in

# Oracle VMs ship with iptables rules that block everything but 22.
# Open 80/443 (Oracle security list must also allow 80/443 in the console):
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Also in the Oracle Cloud console: VCN -> Security List -> add ingress rules
for TCP 80 and 443 from 0.0.0.0/0.

## Get the code + secrets onto the VM (from your machine)

```powershell
# from Windows (repo root); ubuntu = your VM user, <VM_IP> = public IP
ssh ubuntu@<VM_IP> "mkdir -p ~/tracepulse"
scp -r app frontend migrations scripts main.py alembic.ini pyproject.toml uv.lock docker-compose.prod.yml deploy.sh ubuntu@<VM_IP>:~/tracepulse/
scp .env ubuntu@<VM_IP>:~/tracepulse/.env   # secrets are NOT in git
```

(Or if the repo is cloned on the VM: `git pull` inside `~/tracepulse`,
then `scp .env` separately — `.env` never lives in git.)

## Deploy / redeploy (on the VM)

```bash
cd ~/tracepulse
./deploy.sh
```

`deploy.sh` runs `docker compose -f docker-compose.prod.yml up -d --build`,
waits for the API health check, and verifies Caddy serves the SPA and
proxies `/api`. Re-run it any time after `git pull` to redeploy.

## Verify from your machine

```powershell
curl http://<VM_IP>/            # frontend HTML
curl http://<VM_IP>/docs        # FastAPI docs via proxy
curl http://127.0.0.1:8000/docs # only from the VM itself (loopback)
```

## HTTPS with a domain (optional)

Point a domain's A record at the VM's public IP, then on the VM:

```bash
echo 'SITE_ADDRESS=tracepulse.example.com' >> .env   # any subdomain you own
./deploy.sh
```

Caddy automatically obtains and renews Let's Encrypt certificates (stored in
the `caddy_data` volume). Without `SITE_ADDRESS` it serves plain HTTP on `:80`.

## Background jobs (APScheduler)

The SLA monitor and email poller run inside the API process via
`BackgroundScheduler`. On an always-on VM this is exactly right: no
serverless sleep, jobs tick every interval continuously. Do **not** scale the
api service to >1 replica (that would duplicate schedulers); one container is
the intended model.

## Useful commands (on the VM)

```bash
docker compose -f docker-compose.prod.yml ps          # status
docker compose -f docker-compose.prod.yml logs -f api # tail API logs (scheduler/email output here)
docker compose -f docker-compose.prod.yml down        # stop (pgdata volume persists)
```
