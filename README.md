# NAS Media Stack

A self-hosted media automation stack running on a Synology DS1522+. Tell it what you want to watch — it finds, downloads, organises, and serves it to Plex automatically.

---

## How it works

```
 Requests          Indexers          Download          Storage          Playback
─────────────────────────────────────────────────────────────────────────────────
                  ┌─────────┐
                  │ Prowlarr│  ← manages all your torrent/usenet indexers
                  └────┬────┘
                       │ syncs indexers to
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌───────────┐  ┌───────────┐  ┌────────┐
│  Sonarr   │  │  Radarr   │  │ Lidarr │  ← monitor TV / movies / music
└─────┬─────┘  └─────┬─────┘  └───┬────┘
      └───────────────┴────────────┘
                      │ sends download jobs to
             ┌────────┴────────┐
             ▼                 ▼
      ┌────────────┐   ┌──────────┐
      │qBittorrent │   │ SABnzbd  │  ← torrent + usenet download clients
      │ (via VPN)  │   │          │
      └─────┬──────┘   └────┬─────┘
            └───────┬────────┘
                    │ downloads to /data/Downloads/
                    │ Sonarr/Radarr/Lidarr hardlink to /data/Media/
                    ▼
             ┌────────────┐
             │    Plex    │  ← streams your library to any device
             └────────────┘
```

### Services

| Service | Role |
|---------|------|
| **Plex** | Media server — streams to phones, TVs, browsers |
| **Sonarr** | TV show automation — monitors, downloads, imports |
| **Radarr** | Movie automation — same as Sonarr but for movies |
| **Lidarr** | Music automation — same pattern, for albums and tracks |
| **Prowlarr** | Indexer manager — syncs torrent/usenet sources to the *arrs |
| **Bazarr** | Subtitle automation — fetches subtitles for imported content |
| **qBittorrent** | Torrent client — all traffic routes through Gluetun VPN |
| **SABnzbd** | Usenet client |
| **Gluetun** | VPN gateway — qBittorrent's network runs entirely inside it |
| **Seerr** | Request portal — lets others request movies/shows |
| **Tautulli** | Plex analytics — watch history, stream stats, notifications |
| **Recyclarr** | Syncs TRaSH Guide quality profiles into Sonarr/Radarr |
| **Unpackerr** | Watches completed downloads and unpacks archives for import |

### Key concepts

**Hardlinks** — downloads and media share the same `/data` mount. When Sonarr/Radarr import a file they create a hardlink rather than copying it. The file appears in two places but uses disk space only once. qBittorrent keeps seeding the original; Plex reads the media copy.

**VPN kill-switch** — qBittorrent doesn't have its own network interface. It runs inside Gluetun's network namespace, so if the VPN drops qBittorrent loses connectivity rather than falling back to your real IP.

**Internal hostnames** — all containers share a Docker bridge network and talk to each other by service name (`http://sonarr:8989`, `http://radarr:7878`, etc.). No static IPs or port forwarding needed between services.

---

## Scripts

All deployment files live in the `nas/` folder. Copy them to `/volume1/docker/media/` on the NAS.

| File | What it does |
|------|-------------|
| `docker-compose.yml` | Full stack definition |
| `.env` | Your local config and secrets — never committed to git |
| `setup.sh` | Master script — runs all setup steps in order |
| `setup-chmod.sh` | Sets correct permissions on all stack files |
| `setup-folders.sh` | Creates required directories and sets ownership |
| `setup-firewall.sh` | Applies iptables rules and installs them to survive reboots |
| `setup-nordvpn.sh` | Fetches NordVPN WireGuard key and writes it to .env |
| `setup-validate.sh` | Validates configuration before starting the stack |
| `post-deploy-validate.sh` | Validates the stack is working after `docker-compose up` |
| `setup-arr-config.py` | Auto-configures all services via API after first boot |
| `fix-plex-paths.py` | Updates Plex library paths in the database before first boot |
| `fix-qbit-paths.sh` | Updates qBittorrent torrent save paths via API |

---

## Setup

### Step 1: Copy files to the NAS

Copy the contents of `nas/` to `/volume1/docker/media/` on the NAS.

Via SMB — open `\\192.168.1.242` in File Explorer, navigate to `docker/media`, drag in the contents of `nas/`.

Or via SCP:
```bash
scp -r nas/ user@192.168.1.242:/volume1/docker/media/
```

---

### Step 2: Fill in .env

SSH into the NAS and edit the `.env` file:
```bash
nano /volume1/docker/media/.env
```

```env
PUID=1034
PGID=100
TZ=America/New_York           # your timezone
LAN_IP=192.168.1.242          # your NAS LAN IP

PLEX_CLAIM=                   # from https://plex.tv/claim (expires in 4 min — fill in right before Step 4)

SONARR_API_KEY=               # from Sonarr → Settings → General (fill in after first boot)
RADARR_API_KEY=               # from Radarr → Settings → General (fill in after first boot)

QBITTORRENT_USER=admin
QBITTORRENT_PASS=             # choose any password

VPN_PROVIDER=nordvpn
VPN_TYPE=wireguard
NORDVPN_PRIVATE_KEY=          # leave blank — setup-nordvpn.sh fills this in
VPN_COUNTRIES=                # e.g. United States, Netherlands
```

**Getting your NordVPN WireGuard key:**
1. Log in at https://my.nordaccount.com
2. Go to **NordVPN → Manual configuration → WireGuard**
3. Generate a key pair and copy the **Private Key**

---

### Step 3: Run setup.sh

```bash
sudo bash /volume1/docker/media/setup.sh
```

This handles everything in one go:
1. Sets correct permissions on all scripts and config files
2. Creates all required directories with correct ownership
3. Deploys the qBittorrent credential init script
4. Applies iptables firewall rules and installs them to survive reboots
5. Fetches your NordVPN WireGuard key and writes it to `.env`
6. Validates the full configuration

Safe to re-run at any time.

---

### Step 4: Migrate Plex from the native package

> Skip this step if you're doing a fresh install with no existing Plex data.

Stop the native Plex package:
```bash
synopkg stop PlexMediaServer
```

Find where it stored its data:
```bash
find /volume1 -maxdepth 4 -name "Preferences.xml" -path "*/Plex*" 2>/dev/null
```

Copy the data to the Docker config path:
```bash
mkdir -p "/volume1/docker/media/plex/config/Library/Application Support/"

cp -a "/volume1/PlexMediaServer/AppData/Plex Media Server" \
      "/volume1/docker/media/plex/config/Library/Application Support/"
```

Fix ownership:
```bash
PUID=$(grep -m1 '^PUID=' /volume1/docker/media/.env | cut -d'=' -f2-)
PGID=$(grep -m1 '^PGID=' /volume1/docker/media/.env | cut -d'=' -f2-)
chown -R ${PUID}:${PGID} /volume1/docker/media/plex/config/
```

Fix Plex library paths — the native package stored NAS host paths in its database; the Docker container uses `/media` instead:
```bash
# Dry run first to see what changes
python3 /volume1/docker/media/fix-plex-paths.py

# Apply
python3 /volume1/docker/media/fix-plex-paths.py --apply
```

> When migrating from the native package, `PLEX_CLAIM` in `.env` can be left blank — the existing `Preferences.xml` already has your Plex account token.

---

### Step 5: Start the stack

Get a fresh Plex claim token right before running this (it expires in 4 minutes):
1. Go to https://plex.tv/claim
2. Copy the token and set `PLEX_CLAIM=claim-...` in `.env`

Then start:
```bash
cd /volume1/docker/media
docker-compose up -d
```

First run takes a few minutes to pull all images. Watch progress:
```bash
docker-compose logs -f
```

> **Note:** Sonarr, Radarr, and Lidarr will show warnings about missing root folders on first boot. This is expected — fixed in Step 6.

---

### Step 6: Run the auto-configuration script

Once all containers are up, run:
```bash
python3 /volume1/docker/media/setup-arr-config.py
```

What it configures automatically:

| Service | What gets set up |
|---------|-----------------|
| SABnzbd | Download directories, tv/movies/music categories |
| Sonarr | Root folders, qBittorrent + SABnzbd clients, remote path mapping, hardlinks |
| Radarr | Same with movie categories and roots |
| Lidarr | Same with music category and root |
| Prowlarr | Sonarr, Radarr, and Lidarr app connections |
| Bazarr | Sonarr and Radarr connections |
| Seerr | Sonarr and Radarr connections *(after wizard — see Step 7)* |
| Unpackerr | Generates `unpackerr.conf` with API keys pre-filled |
| Recyclarr | Generates starter `recyclarr.yml` with API keys pre-filled |

Safe to re-run — skips anything already configured.

---

### Step 7: Manual configuration

The script handles everything it can via API. The following require manual action:

#### qBittorrent (http://192.168.1.242:49156)

**Watched folder** — Settings → Downloads → Automatically add torrents from: `/downloads/ToFetch`

**Seeding limits** — Settings → BitTorrent → set your preferred ratio (e.g. 2.0) or time limit.

#### Sonarr / Radarr / Lidarr — reassign existing media to new root folders

The script adds the new root folders but existing series/movies still point to old paths. Fix via Mass Editor:

- **Sonarr:** Series → Mass Editor → select all → change root to `/data/Media/TV Shows`
- **Radarr:** Movies → Mass Editor → select all → change root to `/data/Media/Movies`
- Repeat for anime libraries using `/data/Media/Anime/TV Shows` and `/data/Media/Anime/Movies`
- Delete old root folders once empty

#### Prowlarr (http://192.168.1.242:49150)

Add your indexers — Indexers → **+ Add Indexer**. App connections to Sonarr/Radarr/Lidarr are already done by the script.

If migrating from Jackett, delete the old Jackett-based indexers from Sonarr/Radarr/Lidarr → Settings → Indexers after adding replacements in Prowlarr.

#### Seerr (http://192.168.1.242:5056)

1. Complete the setup wizard
2. Connect Plex during the wizard: `http://plex:32400`
3. Re-run `setup-arr-config.py` — it will wire up Sonarr and Radarr automatically

Migrating from Overseerr? Use Settings → Import in Seerr.

#### Tautulli (http://192.168.1.242:8181)

Connect to Plex: `http://plex:32400` and your Plex token
(find it in Plex → Settings → Troubleshooting → Get your X-Plex-Token)

#### Recyclarr

The script generated a starter config at `/volume1/docker/media/recyclarr/config/recyclarr.yml` with your API keys pre-filled. Customise it with the TRaSH Guide quality profiles you want — see https://recyclarr.dev/wiki.

To trigger a manual sync:
```bash
docker exec recyclarr recyclarr sync
```

#### Bazarr — clean up old path mappings

If you had old path mappings referencing `/_video`, delete them. Bazarr now shares the same `/data` mount as Sonarr/Radarr so paths match automatically.

---

### Step 8: Verify end-to-end

1. Confirm Gluetun is connected — the IP should be your VPN's, not your home IP:
   ```bash
   docker exec gluetun wget -qO- https://ipinfo.io
   ```
2. Search for something in Sonarr or Radarr and trigger a manual download
3. Verify qBittorrent downloads to `/downloads/Completed/` (via `/downloads/InProgress/` while active)
4. Verify Sonarr/Radarr activity log says **hardlinked** (not copied)
5. Verify qBittorrent keeps seeding after import
6. Check Plex sees the newly imported media
7. Try requesting something through Seerr

---

## Troubleshooting

**Container won't start**
```bash
docker-compose logs <service>
```

**Permission denied errors**
```bash
id <your-nas-username>
ls -la /volume1/docker/media/
ls -la /volume1/Data/Downloads/
```
Re-run `setup-folders.sh` to fix ownership.

**Plex doesn't see your media**
Library paths inside the Plex container (via the `/media` mount):
- Movies → `/media/Movies`
- TV Shows → `/media/TV Shows`
- Anime Movies → `/media/Anime/Movies`
- Anime TV Shows → `/media/Anime/TV Shows`
- Music → `/media/Music`

Update under Settings → Libraries → Edit → Manage Folders.

**Plex shows a hash code instead of server name / won't play media**
The server wasn't claimed on first boot. Access it directly at `http://192.168.1.242:32400/web` and sign in — it will prompt you to claim it. Once claimed, rename it under Settings.

**Plex "secure connection" warning in browser**
Access Plex via direct IP (`http://192.168.1.242:32400/web`) rather than through `app.plex.tv`, or set Settings → Network → Secure connections to `Preferred`.

**Sonarr/Radarr says "copied" instead of "hardlinked"**
- Enable "Use Hardlinks instead of Copy" in Settings → Media Management
- Verify both downloads and media are under the single `/data` mount

**Sonarr/Radarr gets 403 from SABnzbd**
Re-run `setup-arr-config.py` — it clears SABnzbd's `host_whitelist` which blocks Docker container connections by default.

**qBittorrent can't connect / all torrents stalled**
Gluetun is likely not connected:
```bash
docker-compose logs gluetun
```

**qBittorrent loses its torrent list after restart**
The init script uses a sentinel file (`/config/.credentials-set`) to avoid resetting the config on subsequent boots. If the sentinel file doesn't exist (e.g. first boot after setup), it runs once and creates it. If torrents are lost anyway, the `.torrent` and `.fastresume` files are preserved at `/volume1/docker/media/qbittorrent/config/qBittorrent/BT_Backup/`.

**Stack restart fails — qBittorrent won't connect**
Always restart the full stack with `down && up`, not `restart`:
```bash
docker-compose down && docker-compose up -d
```
`restart` brings everything up simultaneously without respecting dependency order — qBittorrent tries to join Gluetun's network before Gluetun is ready.

**Old NAS IP references lingering in service configs**
Search for `192.168.1.241` in each service's settings and replace with the container hostname from the internal hostnames table below.

---

## Quick Reference

### Service URLs

| Service      | URL                              |
|--------------|----------------------------------|
| Plex         | http://192.168.1.242:32400/web   |
| Sonarr       | http://192.168.1.242:49152       |
| Radarr       | http://192.168.1.242:49151       |
| Lidarr       | http://192.168.1.242:49154       |
| Prowlarr     | http://192.168.1.242:49150       |
| Bazarr       | http://192.168.1.242:49153       |
| SABnzbd      | http://192.168.1.242:49155       |
| qBittorrent  | http://192.168.1.242:49156       |
| Seerr        | http://192.168.1.242:5056        |
| Tautulli     | http://192.168.1.242:8181        |

### Internal Hostnames

Use these when connecting services to each other inside Docker.
`setup-arr-config.py` handles this automatically — only needed for manual configuration.

> **qBittorrent:** shares Gluetun's network namespace. Use `gluetun` as the hostname and `49156` as the port when adding it as a download client.

| Service      | Hostname  | Port  |
|--------------|-----------|-------|
| Plex         | plex      | 32400 |
| Sonarr       | sonarr    | 8989  |
| Radarr       | radarr    | 7878  |
| Lidarr       | lidarr    | 8686  |
| Prowlarr     | prowlarr  | 9696  |
| Bazarr       | bazarr    | 6767  |
| SABnzbd      | sabnzbd   | 8080  |
| qBittorrent  | gluetun   | 49156 |
| Seerr        | seerr     | 5055  |
| Tautulli     | tautulli  | 8181  |

### Docker Compose Cheatsheet

All commands run from `/volume1/docker/media/`.

**Everyday**
```bash
docker-compose ps                                    # container status
docker-compose up -d                                 # start all (or start stopped containers)
docker-compose down && docker-compose up -d          # full restart (respects dependency order)
docker-compose restart sonarr                        # restart one container
docker-compose stop sonarr && docker-compose start sonarr
```

**Updates**
```bash
docker-compose pull                  # pull latest images for all services
docker-compose pull sonarr           # pull latest for one service
docker-compose up -d                 # recreate containers that have a newer image
```

**Logs**
```bash
docker-compose logs sonarr           # recent logs
docker-compose logs -f sonarr        # live logs (Ctrl+C to stop)
docker-compose logs --tail=50 sonarr
docker-compose logs -f               # all services
```

**Debugging**
```bash
docker-compose exec sonarr bash                        # shell inside container
docker exec gluetun wget -qO- https://ipinfo.io        # check VPN IP
docker stats                                           # live CPU/memory
docker-compose config                                  # resolved config with .env applied
docker inspect sonarr                                  # full container details
```

**Cleanup**
```bash
docker image prune                   # remove unused images
docker system prune                  # remove stopped containers, unused networks, dangling images
```
