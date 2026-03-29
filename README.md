# NAS Media Stack Setup Guide

## Prerequisites
- New DS1522+ with DSM installed
- All media files already at `/volume1/Data/Media/`
- All config folders already at `/volume1/docker/media/`
- Container Manager (Docker) installed from Package Center

## What's changed from the old setup
- **Plex** moved from native Synology package to Docker (portable, easier updates)
- **Jackett** replaced by **Prowlarr** (auto-syncs indexers to Sonarr/Radarr/Lidarr)
- **Overseerr** replaced by **Seerr** (Overseerr is deprecated — Seerr is its maintained successor)
- **Tautulli** added (Plex stats and monitoring)
- **Lidarr** added (music automation, same pattern as Sonarr/Radarr)
- **Recyclarr** added (auto-syncs TRaSH Guide quality profiles into Sonarr/Radarr)
- **Gluetun** added (VPN kill-switch — all qBittorrent traffic routes through it)
- **All containers** on a shared Docker network (talk to each other by name, no hardcoded IPs)
- **Unified `/data` mount** across all containers (enables hardlinks — no more doubled disk usage on imports)
- **PUID/PGID standardized** to 1034/100 across all containers (was inconsistent before)
- **API keys** moved to `.env` file (no longer hardcoded in docker run commands)

## What you need to do manually

Most of this stack is automated, but some things require human action. Here's everything that can't be scripted:

### Before first boot
- [ ] Get WireGuard credentials from your VPN provider (private key, addresses, server country)
- [ ] Get a Plex claim token from https://plex.tv/claim (wait until right before `docker-compose up`)
- [ ] Fill in the `.env` file with all values (Step 2)
- [ ] Create config directories on the NAS (Step 3)
- [ ] Fix file ownership for Seerr config dir: `chown -R 1034:100 /volume1/docker/media/seerr`
- [ ] Migrate Plex data from the native package (Step 4)

### After first boot
- [ ] Update root folder paths in Sonarr, Radarr, and Lidarr (Step 9)
- [ ] Set download client paths in qBittorrent and SABnzbd (Step 9)
- [ ] Connect Sonarr/Radarr/Lidarr to qBittorrent and SABnzbd as download clients (Step 9)
- [ ] Add your indexers in Prowlarr and connect it to all *arr apps (Step 11)
- [ ] Set up Seerr and connect it to Plex, Sonarr, Radarr (Step 13)
- [ ] Set up Tautulli and connect it to Plex (Step 13)
- [ ] Edit Recyclarr config at `/volume1/docker/media/recyclarr/config/recyclarr.yml` with API keys and desired quality profiles (Step 13)
- [ ] Verify Gluetun VPN is working before downloading anything (Step 13)

### Getting your NordVPN WireGuard private key
1. Log in at https://my.nordaccount.com
2. Go to **NordVPN → Manual configuration → Service credentials**
3. Under the WireGuard section, generate a key pair
4. Copy the **Private Key** — that's your `NORDVPN_PRIVATE_KEY`

NordVPN handles the server addresses automatically, so no `VPN_ADDRESSES` is needed.

---

## How downloads and seeding work with this setup

```
1. Sonarr/Radarr/Lidarr send a download to qBittorrent or SABnzbd
2. Download goes to /data/Downloads/Torrents/InProgress/ (or /data/Downloads/Usenet/)
3. When complete, Sonarr/Radarr/Lidarr create a HARDLINK in /data/Media/
   - Same file, two paths, NO extra disk space used
   - The original stays in the download folder for seeding
4. qBittorrent keeps seeding from the original path (through Gluetun VPN)
5. When you eventually remove the torrent, only the download copy is deleted
   - The media copy in /data/Media/ stays untouched
```

For usenet: SABnzbd downloads are copied (not hardlinked) since they're typically
extracted from archives. The download copy can be cleaned up after import.

---

## Step 1: Copy the compose files to the NAS

Copy `docker-compose.yml` and `.env` to `/volume1/docker/media/` on the NAS.

Via SMB — open `\\192.168.1.242` in File Explorer, navigate to `docker/media`, drag them in.

Or via SCP:
```bash
scp docker-compose.yml .env user@192.168.1.242:/volume1/docker/media/
```

## Step 2: Fill in the .env file

SSH into the NAS and edit the `.env` file:
```bash
nano /volume1/docker/media/.env
```

Required variables:
```
PUID=1034
PGID=100
TZ=America/New_York        # your timezone
LAN_IP=192.168.1.242       # your NAS LAN IP

PLEX_CLAIM=                # from https://plex.tv/claim (expires in 4 min — fill in right before Step 6)

SONARR_API_KEY=            # from Sonarr → Settings → General
RADARR_API_KEY=            # from Radarr → Settings → General

# Gluetun VPN (NordVPN)
NORDVPN_PRIVATE_KEY=       # from my.nordaccount.com → NordVPN → Manual config → WireGuard
VPN_COUNTRIES=             # e.g. United States, Netherlands, Switzerland
```

Save and exit (`Ctrl+X`, `Y`, `Enter`).

## Step 3: Create config folders for new services

SSH into the NAS and run:
```bash
mkdir -p /volume1/docker/media/plex/config \
         /volume1/docker/media/prowlarr/config \
         /volume1/docker/media/qbittorrent/config \
         /volume1/docker/media/tautulli/config \
         /volume1/docker/media/seerr/config \
         /volume1/docker/media/sabnzbd/config \
         /volume1/docker/media/unpackerr/config \
         /volume1/docker/media/radarr/config \
         /volume1/docker/media/sonarr/config \
         /volume1/docker/media/bazarr/config \
         /volume1/docker/media/lidarr/config \
         /volume1/docker/media/recyclarr/config
```

Existing service configs (sonarr, radarr, sabnzbd, bazarr, unpackerr) are already in place from the migration.

## Step 4: Migrate Plex data from native app

Find your Plex data on the NAS. Check:
```bash
ls /volume1/PlexMediaServer/
ls /volume1/Plex/
```
Copy it into the Docker config path:
```bash
cp -r "/volume1/PlexMediaServer/AppData/Plex Media Server/"* /volume1/docker/media/plex/config/
```
Adjust the source path to wherever your Plex data actually lives.

If the native Plex package is installed, **stop and disable it**:
Package Center → Plex Media Server → Stop → set to not auto-start.

## Step 5: Fix file permissions

The old setup used inconsistent user IDs. The new setup standardizes to 1034/100:
```bash
chown -R 1034:100 /volume1/docker/media/sabnzbd
chown -R 1034:100 /volume1/Data/Downloads/Usenet
```

Seerr config dir needs the same ownership as everything else:
```bash
chown -R 1034:100 /volume1/docker/media/seerr
```

## Step 6: Get a Plex claim token

1. Go to https://plex.tv/claim
2. Copy the token (starts with `claim-`)
3. Add it to the `PLEX_CLAIM=` line in `/volume1/docker/media/.env`

**The token expires in 4 minutes — do this right before Step 7.**

## Step 7: Start everything

```bash
cd /volume1/docker/media
docker-compose up -d
```
First run takes a few minutes to download all images. Watch progress with:
```bash
docker-compose logs -f
```
Press `Ctrl+C` to stop watching logs (containers keep running).

## Step 8: Verify all services load

**Expected:** Sonarr, Radarr, and Lidarr will show warnings about missing root folders.
This is normal — fix this in Step 9.

Open each in your browser:

| Service      | URL                              |
|--------------|----------------------------------|
| Plex         | http://192.168.1.242:32400/web   |
| Sonarr       | http://192.168.1.242:49152       |
| Radarr       | http://192.168.1.242:49151       |
| Lidarr       | http://192.168.1.242:49154       |
| Prowlarr     | http://192.168.1.242:49150       |
| SABnzbd      | http://192.168.1.242:49155       |
| qBittorrent  | http://192.168.1.242:49156       |
| Bazarr       | http://192.168.1.242:49153       |
| Seerr        | http://192.168.1.242:5056        |
| Tautulli     | http://192.168.1.242:8181        |

Recyclarr and Unpackerr have no web UI — they run silently in the background.

## Step 9: Update paths in all services

All containers now mount `/volume1/Data` as `/data`. The old paths (`/downloads`,
`/movies`, `/tv/shows`, etc.) no longer exist inside the containers. Update each
service to use the new paths:

### qBittorrent (http://192.168.1.242:49156)
Settings → Downloads:
- Default Save Path: `/data/Downloads/Torrents/InProgress`

### SABnzbd (http://192.168.1.242:49155)
Settings → Folders:
- Completed Download Folder: `/data/Downloads/Usenet`
- (Incomplete stays at `/incomplete-downloads` — unchanged)

### Sonarr (http://192.168.1.242:49152)

**Root folders** — Settings → Media Management → Root Folders:
1. Add new root folder: `/data/Media/TV Shows`
2. Add new root folder: `/data/Media/Anime/TV Shows`
3. Go to **Series → Mass Editor** (select all series)
4. Change root folder from `/tv/shows` → `/data/Media/TV Shows`
5. Do the same for anime: `/tv/anime` → `/data/Media/Anime/TV Shows`
6. Now delete the old root folders (`/tv/shows`, `/tv/anime`)

**Hardlinks** — Settings → Media Management (scroll down):
- **Use Hardlinks instead of Copy** = Yes

**Download clients** — Settings → Download Clients:
- qBittorrent: host = `qbittorrent`, port = `8080`
- SABnzbd: host = `sabnzbd`, port = `8080`
- **Delete any Remote Path Mappings** (no longer needed)

### Radarr (http://192.168.1.242:49151)

**Root folders** — Settings → Media Management → Root Folders:
1. Add new root folder: `/data/Media/Movies`
2. Add new root folder: `/data/Media/Anime/Movies`
3. Go to **Movies → Mass Editor** (select all movies)
4. Change root folder from `/movies` → `/data/Media/Movies`
5. Do the same for anime: `/anime/movies` → `/data/Media/Anime/Movies`
6. Now delete the old root folders (`/movies`, `/anime/movies`)

**Hardlinks** — Settings → Media Management (scroll down):
- **Use Hardlinks instead of Copy** = Yes

**Download clients** — Settings → Download Clients:
- qBittorrent: host = `qbittorrent`, port = `8080`
- SABnzbd: host = `sabnzbd`, port = `8080`
- **Delete any Remote Path Mappings** (no longer needed)

### Lidarr (http://192.168.1.242:49154)

**Root folders** — Settings → Media Management → Root Folders:
1. Add root folder: `/data/Media/Music`

**Hardlinks** — Settings → Media Management (scroll down):
- **Use Hardlinks instead of Copy** = Yes

**Download clients** — Settings → Download Clients:
- qBittorrent: host = `qbittorrent`, port = `8080`
- SABnzbd: host = `sabnzbd`, port = `8080`

### Bazarr (http://192.168.1.242:49153)

**Connections** — Settings:
- Sonarr: host = `sonarr`, port = `8989`
- Radarr: host = `radarr`, port = `7878`

**Path mappings** — Delete any old path mappings that reference `/_video`.
Bazarr now uses the same `/data` mount as Sonarr/Radarr, so paths match
automatically and no mappings are needed.

### Unpackerr
No UI — configured via environment variables in the compose file.
Unpackerr gets download paths from Sonarr/Radarr via API, so it automatically
picks up the new `/data/Downloads/...` paths. No changes needed.

## Step 10: Configure qBittorrent seeding behavior

In qBittorrent (http://192.168.1.242:49156):
- Settings → BitTorrent → Seeding Limits: set your preferred ratio (e.g., 2.0) or time limit
- Do NOT enable "When ratio is reached → Remove torrent" unless you want automatic cleanup
- Sonarr/Radarr will not delete the download while qBittorrent is still seeding

## Step 11: Set up Prowlarr (replaces Jackett)

1. Open Prowlarr at http://192.168.1.242:49150
2. Settings → Apps → add **Sonarr**:
   - Prowlarr Server = `http://prowlarr:9696`
   - Sonarr Server = `http://sonarr:8989`
   - API Key = (from Sonarr → Settings → General)
3. Settings → Apps → add **Radarr**:
   - Prowlarr Server = `http://prowlarr:9696`
   - Radarr Server = `http://radarr:7878`
   - API Key = (from Radarr → Settings → General)
4. Settings → Apps → add **Lidarr**:
   - Prowlarr Server = `http://prowlarr:9696`
   - Lidarr Server = `http://lidarr:8686`
   - API Key = (from Lidarr → Settings → General)
5. Indexers → add your indexers (same ones you had in Jackett)
6. Prowlarr automatically syncs them to Sonarr, Radarr, and Lidarr

## Step 12: Clean up old Jackett indexers

In **Sonarr**, **Radarr**, and **Lidarr** → Settings → Indexers:
Delete all old Jackett-based indexers. Prowlarr has already synced its own.

## Step 13: Set up new services

### Seerr (http://192.168.1.242:5056)
1. First launch walks you through setup
2. Connect to Plex: use `http://plex:32400`
3. Connect to Sonarr: use `http://sonarr:8989` + API key
4. Connect to Radarr: use `http://radarr:7878` + API key
5. Share the URL with anyone you want to let request movies/shows

**Migrating from Overseerr?** Seerr has a built-in migration tool under Settings → Import.

### Tautulli (http://192.168.1.242:8181)
1. First launch walks you through setup
2. Connect to Plex: use `http://plex:32400`

### Recyclarr
No web UI. On first boot it creates a starter config at:
`/volume1/docker/media/recyclarr/config/recyclarr.yml`

Edit it to add your Sonarr/Radarr URLs and API keys, then enable the TRaSH Guide
quality profiles you want. See https://recyclarr.dev/guide for full documentation.

Example config snippet:
```yaml
sonarr:
  main:
    base_url: http://sonarr:8989
    api_key: your-sonarr-api-key
    quality_profiles:
      - name: WEB-1080p

radarr:
  main:
    base_url: http://radarr:7878
    api_key: your-radarr-api-key
    quality_profiles:
      - name: HD Bluray + WEB
```

Recyclarr will sync on every container restart. To trigger a manual sync:
```bash
docker exec recyclarr recyclarr sync
```

### Gluetun (VPN)
Gluetun runs silently and routes all qBittorrent traffic through your VPN. Verify
it's working after startup:
```bash
docker exec gluetun wget -qO- https://ipinfo.io
```
The IP shown should be your VPN's IP, not your home IP. If qBittorrent can't connect
at all, check Gluetun's logs first:
```bash
docker-compose logs gluetun
```

## Step 14: Test end-to-end

1. Verify Gluetun is connected (see Step 13 above)
2. Search for something in Sonarr or Radarr
3. Trigger a manual download via torrent — verify:
   - qBittorrent downloads to `/data/Downloads/Torrents/InProgress/`
   - Sonarr/Radarr imports it to `/data/Media/`
   - qBittorrent keeps seeding after import
   - Check Sonarr/Radarr activity log says "hardlinked" (not "copied")
4. Trigger a manual download via usenet — verify SABnzbd + import works
5. Check Plex sees newly imported media
6. Try requesting something through Seerr

---

## Troubleshooting

**Container won't start?**
```bash
docker-compose logs <service-name>
```

**Permission denied errors?**
Check your user ID and file ownership match:
```bash
id <your-nas-username>
ls -la /volume1/docker/media/
ls -la /volume1/Data/Downloads/
```

**Plex doesn't see your media?**
Plex uses separate mounts (not `/data`). Library paths should be:
- Movies → `/movies`
- TV Shows → `/tv/shows`
- Anime Movies → `/anime/movies`
- Anime TV → `/anime/tv`

**Sonarr/Radarr/Lidarr shows missing root folder errors?**
Expected on first boot. Follow Step 9 to add new root folders and reassign.

**Sonarr/Radarr says "copied" instead of "hardlinked"?**
- Verify "Use Hardlinks instead of Copy" is enabled in Settings → Media Management
- This should work because downloads and media are both under the single `/data` mount

**Sonarr/Radarr can't find downloads?**
Old paths like `/downloads` or `/Downloads/complete` no longer exist.
Download paths are now under `/data/Downloads/`. Update the download client config in Step 9.

**Torrents stop seeding after import?**
In Sonarr/Radarr → Settings → Download Clients:
- "Completed Download Handling → Remove" should be set to a condition you're comfortable with
  (e.g., after reaching seed ratio), or set to "Never" and manage cleanup in qBittorrent

**Bazarr can't find media files?**
Delete any old path mappings that reference `/_video`. Bazarr now shares the
same `/data` mount as Sonarr/Radarr — paths match automatically.

**qBittorrent can't connect / all torrents stalled?**
Gluetun is likely not connected. Check VPN credentials in `.env` and review logs:
```bash
docker-compose logs gluetun
```

**Old NAS IP references lingering?**
Search each service's settings for `192.168.1.241` and replace with the container
hostname from the cheatsheet.
