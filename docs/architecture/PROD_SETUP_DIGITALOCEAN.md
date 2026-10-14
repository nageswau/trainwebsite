# Production Setup — DigitalOcean (edusphere.org.uk)

**Authority:** `DEC-INFRA-002` in `docs/decisions/PRODUCT_DECISION_REGISTER.md` (owner-confirmed
2026-10-14). Prod gets a **new droplet** running this repo's `docker compose` stack. The database
is **DigitalOcean Managed PostgreSQL** and uploaded files live on a **Block Storage Volume**. The
current droplet stays as `dev.edusphere.org.uk`.

Sizes, versions and settings below follow `DEC-INFRA-002` ID1–ID9. Those are recommended defaults,
**`UNVERIFIED`**. Change them here and in the register if you choose differently.

Deploy from `main`. It must include PR #282 (web build memory fix) and PR #281 (DEC-INFRA-002).

---

## 1. Target layout

```
                    DNS: edusphere.org.uk, api.edusphere.org.uk
                                     │
                              Reserved IP
                                     │
 ┌──────────────── Prod droplet (4 GB / 2 vCPU, VPC) ────────────────┐
 │  Caddy :80/:443 (TLS)                                              │
 │    ├── web  (Next.js, 127.0.0.1:3000) ── proxies /api/v1, /local-files
 │    └── api  (FastAPI, 127.0.0.1:8000) ── runs Alembic on start     │
 │  worker (Celery)   beat (Celery scheduler)   redis (queue, AOF)     │
 │                                                                     │
 │  /mnt/edusphere_data  ← Block Storage Volume                        │
 │     ├── uploads/       → docker volume edusphere_uploads (/data/uploads)
 │     ├── caddy_data/    → TLS certificates                           │
 │     └── caddy_config/                                               │
 └──────────────────────────────────┬──────────────────────────────────┘
                                    │ private network (VPC), TLS
                     Managed PostgreSQL 16 (daily backups + PITR)
```

| Data | Where | Backed up by |
|---|---|---|
| Database | Managed PostgreSQL | DO daily backups + point-in-time restore (7 days) |
| Uploaded files (documents, photos, generated PDFs) | Volume `uploads/` | Daily Volume snapshot (§9). Droplet backups do **not** include Volumes |
| TLS certificates | Volume `caddy_data/` | Volume snapshot. Caddy re-issues them if lost |
| Job queue | `redis` container (droplet disk) | Not backed up. It is transient and beat re-schedules |
| Code | Git `main` | GitHub |
| Secrets | `.env` on the droplet | Keep a copy in your password manager |

---

## 2. Before you start

- [ ] DigitalOcean account with billing, and a Project named `EduSphere Production`.
- [ ] Access to the DNS for `edusphere.org.uk`.
- [ ] An SSH key on your PC (`ssh-keygen -t ed25519`), added to DO → Settings → Security.
- [ ] **Region chosen.** Put the droplet, database and Volume all in the same region.
  - Region and data residency are still open in `DEPLOYMENT.md`: `NEEDS_CONFIRMATION`.
  - For India-based users, `BLR1` gives the lowest latency. For UK/EU users, use `LON1`.
- [ ] Live credentials only for integrations you launch with: Razorpay live keys, SMTP account,
      Twilio, Zoho, Google.
- [ ] Your local checkout is on `main` and up to date (`git checkout main && git pull`).

---

## 3. Create the DigitalOcean resources

Create in this order, all in the chosen region and the same VPC.

### 3.1 Droplet
- Ubuntu 24.04 LTS, Basic, **4 GB / 2 vCPU** (Regular SSD is fine).
- Authentication: SSH key only. Enable **Monitoring** and **weekly Backups**.
- Hostname: `edusphere-prod`. Project: `EduSphere Production`.

### 3.2 Reserved IP
- Networking → Reserved IPs → assign to `edusphere-prod`. DNS points here, so you can replace the
  droplet later without a DNS change.

### 3.3 Managed PostgreSQL
- Databases → Create → PostgreSQL **16**, same region and VPC.
- Plan: **2 GB RAM / 1 vCPU** basic node.
  - The app uses SQLAlchemy's default pools: up to 15 connections per process.
  - The api plus 2 Celery worker processes can reach about 45 connections. The 1 GB node's limit
    is around 20.
  - Check the exact limit on the cluster's Overview page.
- Add a standby node later if you need automatic failover.
- Name: `edusphere-prod-db`.
- Once it's online:
  1. **Settings → Trusted sources:** add the droplet `edusphere-prod` only.
  2. **Users & Databases:** create database `edusphere` and user `edusphere`. Copy the user's
     password.
  3. **Connection details → VPC network:** note the private host (`private-…db.ondigitalocean.com`)
     and port `25060`.

### 3.4 Volume
- Volumes → Create → **20 GB**, attach to `edusphere-prod`, "Manually format & mount", name
  `edusphere-data`.

### 3.5 Cloud Firewall
- Networking → Firewalls → `edusphere-prod-fw`, applied to the droplet.
  - Inbound: SSH 22 from **your IP only**, HTTP 80 and HTTPS 443 from all.
  - Outbound: all.

---

## 4. Prepare the droplet

SSH in as root once (`ssh root@<reserved-ip>`):

```bash
adduser deploy && usermod -aG sudo deploy
rsync -a ~/.ssh /home/deploy/ && chown -R deploy: /home/deploy/.ssh
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

apt update && apt -y upgrade && apt -y install unattended-upgrades fail2ban rsync
dpkg-reconfigure -f noninteractive unattended-upgrades

curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy

fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
timedatectl set-timezone UTC          # app schedules are written in UTC
```

From here on, work as `deploy` (`ssh deploy@<reserved-ip>`).

---

## 5. Mount the Volume and make Docker wait for it

```bash
sudo mkfs.ext4 /dev/disk/by-id/scsi-0DO_Volume_edusphere-data
sudo mkdir -p /mnt/edusphere_data
echo '/dev/disk/by-id/scsi-0DO_Volume_edusphere-data /mnt/edusphere_data ext4 defaults,nofail,discard,noatime 0 2' | sudo tee -a /etc/fstab
sudo mount -a && df -h /mnt/edusphere_data

sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nRequiresMountsFor=/mnt/edusphere_data\n' | sudo tee /etc/systemd/system/docker.service.d/volume-mount.conf
sudo systemctl daemon-reload && sudo systemctl restart docker
```

Bind the Compose named volumes to the Volume **before the first `up`**:

```bash
VOL=/mnt/edusphere_data; P=edusphere      # P = compose project = folder name /home/deploy/edusphere
for v in uploads caddy_data caddy_config; do
  sudo mkdir -p $VOL/$v
  docker volume create --driver local --opt type=none --opt o=bind --opt device=$VOL/$v \
    --label com.docker.compose.project=$P --label com.docker.compose.volume=$v ${P}_$v
done
docker volume inspect ${P}_uploads --format '{{.Options.device}}'   # → /mnt/edusphere_data/uploads
```

If Compose ever asks "Volume … exists but doesn't match configuration… Recreate?", answer **N**.

---

## 6. Prepare the database

Managed PostgreSQL makes `doadmin` the owner of new databases. Hand `edusphere` ownership so that
Alembic can create tables. Use the **doadmin** connection string from the console:

```bash
docker run --rm -it postgres:16-alpine psql "postgresql://doadmin:<doadmin-pw>@<private-host>:25060/edusphere?sslmode=require" \
  -c "ALTER DATABASE edusphere OWNER TO edusphere;" \
  -c "ALTER SCHEMA public OWNER TO edusphere;"
```

The schema itself is created by the api's Alembic migrations on first start (§8). No extensions are
required.

---

## 7. DNS

At your DNS provider (lower TTL to 300 a day before):

| Type | Name | Value |
|---|---|---|
| A | `edusphere.org.uk` (@) | reserved IP |
| A | `api.edusphere.org.uk` | reserved IP |

Don't add `www` yet. The `Caddyfile` serves only `WEB_DOMAIN` and `API_DOMAIN`, so `www` would get
no certificate. Adding it needs a Caddyfile change. Check propagation with
`nslookup edusphere.org.uk` before §8, so that Caddy can obtain certificates first time.

---

## 8. Deploy the code

### 8.1 Copy
From your PC, in the repo on `main`:
```powershell
./scripts/deploy-copy-to-droplet.ps1 -DropletIp <reserved-ip>
```
This creates `/home/deploy/edusphere`. The project name `edusphere` matches §5.

### 8.2 Create `/home/deploy/edusphere/.env`
Start with `cp .env.example .env`, then set:

| Variable | Prod value | Why |
|---|---|---|
| `ENVIRONMENT` | `production` | Hides the demo-accounts box on login pages |
| `SECRET_KEY` | output of `openssl rand -hex 32` | Never reuse dev's |
| `DATABASE_URL` | `postgresql+asyncpg://edusphere:<pw>@<private-host>:25060/edusphere?ssl=require` | asyncpg form: `ssl=require`, **not** `sslmode=` |
| `REDIS_URL` | `redis://redis:6379/0` (unchanged) | Redis stays in compose |
| `FRONTEND_URL` | `https://edusphere.org.uk` | CORS origin and links in emails |
| `COOKIE_SECURE` | `true` | HTTPS-only cookies |
| `AUTO_CREATE_SCHEMA` | `false` | Alembic owns the schema |
| `AWS_S3_BUCKET` | *(empty)* | Empty = local storage on the Volume (§10 for Spaces) |
| `LOCAL_UPLOAD_DIR` | `/data/uploads` | Bound to the Volume |
| `WEB_DOMAIN` / `API_DOMAIN` | `edusphere.org.uk` / `api.edusphere.org.uk` | Caddy sites |
| `API_PORT` / `WEB_PORT` | `127.0.0.1:8000` / `127.0.0.1:3000` | Only Caddy is public |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS` | your mail provider; from e.g. `noreply@edusphere.org.uk` | Invite and notification emails. Set SPF/DKIM for the domain |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | live keys | Payments |
| `TWILIO_*`, `ZOHO_*`, `GOOGLE_*`, `*_WEBHOOK_URL` | only for integrations you launch | Blank = recorded as not configured |

Then lock the file down with `chmod 600 .env`, and store a copy in your password manager.

### 8.3 Build and start
The local `postgres` service must **never** start in prod, so list the services explicitly. Use
this same command for every deploy:

```bash
cd /home/deploy/edusphere
export COMPOSE="docker compose -f docker-compose.yml -f docker-compose.override.yml"
$COMPOSE up -d --build redis api worker beat web caddy
$COMPOSE ps
$COMPOSE logs api | grep -iE 'alembic|error|startup_complete' | tail -20
```

The first build takes a while; the web build is heavy even with the memory fix. Migrations run
automatically when the api starts. `startup_complete` means the api is ready.

### 8.4 Create the real admin accounts
```bash
$COMPOSE exec -e SUPER_ADMIN_EMAIL=you@edusphere.org.uk -e SUPER_ADMIN_PASSWORD='<strong-unique>' \
  api python -m app.bootstrap_admin
```
Optionally add the `IT_ADMIN_*` and `OVERSEAS_ADMIN_*` pairs. **Never run `app/seed.py` in prod**:
it creates demo accounts with the published password `Demo@123`. Never copy the dev database
either.

### 8.5 Integrations
- Razorpay dashboard → Webhooks: `https://api.edusphere.org.uk/api/v1/payments/webhooks/razorpay`,
  secret = `RAZORPAY_WEBHOOK_SECRET`.
- Update any other provider callback URLs that point at dev to the prod domains.

---

## 9. Backups and monitoring

### 9.1 Database
- Managed PostgreSQL takes daily backups automatically and offers point-in-time restore.
- **Before launch, do one test restore:** Databases → `edusphere-prod-db` → Backups → Restore to a
  new cluster. Check that tables exist, then delete the test cluster.
- Optional off-DigitalOcean copy (weekly):
  `docker run --rm postgres:16-alpine pg_dump "<edusphere-uri>?sslmode=require" -Fc > edusphere-$(date +%F).dump`,
  then download it.

### 9.2 Uploaded files (Volume)
Droplet backups exclude Volumes, so snapshot the Volume daily. Create an API token at DO → API,
with custom scope **block_storage read/write** only. Then on the droplet:

```bash
sudo snap install doctl && doctl auth init        # paste the scoped token
doctl compute volume list --format ID,Name        # note the volume ID
crontab -e
# 03:00 UTC daily snapshot; keep the newest 7
0 3 * * * doctl compute volume snapshot <volume-id> --snapshot-name edusphere-data-$(date +\%F) && doctl compute snapshot list --resource volume --format ID,Name --no-header | grep edusphere-data- | sort -k2 | head -n -7 | awk '{print $1}' | xargs -r -n1 doctl compute snapshot delete -f
```

### 9.3 Monitoring
- **Monitoring → Uptime:** checks on `https://edusphere.org.uk` and
  `https://api.edusphere.org.uk/health`, with email alerts.
- **Monitoring → Alerts:** droplet CPU > 80%, memory > 80%, disk > 80%. Volume usage > 70%
  (`df -h /mnt/edusphere_data`). Database CPU and connections > 80%.
- **Logs:** `$COMPOSE logs --tail 200 api worker web caddy`.

---

## 10. Go-live checklist

- [ ] `https://edusphere.org.uk` loads with a valid certificate.
- [ ] `https://api.edusphere.org.uk/health` returns `"environment":"production"`.
- [ ] The login page shows **no** "Demo accounts" box.
- [ ] Super admin can log in. In browser devtools the session cookie is marked `Secure`.
- [ ] Uploading a document works, and the file appears under `/mnt/edusphere_data/uploads/`.
- [ ] A generated PDF (certificate or billing) opens.
- [ ] An invite email arrives, and its link points to `https://edusphere.org.uk`.
- [ ] `$COMPOSE logs worker beat` shows scheduled tasks running without errors.
- [ ] Razorpay test payment and webhook reach prod (then switch to live mode).
- [ ] Test restore of the database done (§9.1). First Volume snapshot exists (§9.2).
- [ ] `sudo reboot`. Afterwards the Volume is mounted, all six containers are up and the site works.
- [ ] `.env` is saved in the password manager, and dev and prod secrets differ.

---

## 11. Day-2 operations

| Task | How |
|---|---|
| Deploy a new version | Merge to `main` → test on dev droplet → `./scripts/deploy-copy-to-droplet.ps1 -DropletIp <reserved-ip>` → `$COMPOSE up -d --build redis api worker beat web caddy` |
| Never | `docker compose down -v` (drops the volume bindings; next `up` would create empty volumes), `app/seed.py`, starting the `postgres` service |
| Roll back code | Re-deploy the previous `main` commit the same way. If a migration must be undone, restore the database to a point in time just before the deploy (§9.1) |
| Restore files | Volumes → Snapshots → create a Volume from the snapshot, attach, `rsync` the needed files into `/mnt/edusphere_data/uploads/` |
| Resize | Droplet: power off → Resize. Database: Settings → resize (online). Volume: Increase size, then `sudo resize2fs /dev/disk/by-id/scsi-0DO_Volume_edusphere-data` |
| OS updates | unattended-upgrades applies security patches. Reboot monthly, in a quiet hour |

---

## 12. When to move files from the Volume to Spaces

Stay on the Volume while all of these hold:
- One app droplet.
- Uploads under about 50 GB.
- Daily snapshots are an acceptable recovery point.

**Move to Spaces when any of these happens:**
1. **A second app droplet or App Platform.** A Volume attaches to only one droplet, so several app
   servers can't share it. This is the hard trigger.
2. **Uploads pass about 50 GB, or Volume use stays above 70%.** Spaces grows without resizing and
   costs less per GB at that scale.
3. **Large public media**, such as course videos or public-site images. Spaces CDN serves them
   without loading the droplet.
4. **You need file-level versioning or cross-region copies** that daily snapshots don't give.

**What the move involves (needs its own Feature ID before coding):**
1. **Code:**
   - Every `boto3.client("s3", …)` call (`services/storage.py`, `services/billing_documents.py`,
     `services/certificates.py`, `api/public.py`) must reach Spaces. Either pass
     `endpoint_url=https://<region>.digitaloceanspaces.com`, or set `AWS_ENDPOINT_URL_S3` (honoured
     by boto3 ≥ 1.35).
   - Verify that `ServerSideEncryption="AES256"` and presigned PUT/GET work on Spaces. Drop or gate
     the SSE argument if they don't.
   - Configure the bucket's CORS for browser uploads from `https://edusphere.org.uk`.
2. **Infra:**
   - Create a Spaces bucket (private, same region) and a Spaces access key.
   - Set `AWS_S3_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and the
     endpoint in `.env`.
3. **Data:** stop `api` and `worker`, then copy the files so their keys stay the same:
   `rclone copy /mnt/edusphere_data/uploads spaces:<bucket>`. Stored keys look like
   `uploads/<uuid>-<name>`, relative to `LOCAL_UPLOAD_DIR`. Start the services again, spot-check
   downloads, and keep the Volume for 30 days before deleting it.

---

## 13. Still open

- Region and data residency (`NEEDS_CONFIRMATION`, §2).
- `www.edusphere.org.uk` (needs a Caddyfile site block or a redirect).
- CDN in front of the site; separate UAT environment.
- Managed Redis. Not needed now; revisit together with the Spaces trigger 1.
- The ID1–ID9 sizing and settings in `DEC-INFRA-002` remain `UNVERIFIED` until you confirm them.
