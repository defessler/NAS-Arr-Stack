# NAS Media Stack Setup Guide

## Overview

This is a self-hosted media automation stack running on a Synology DS1522+ NAS. The idea is simple: you tell it what you want to watch, and it finds, downloads, organises, and serves it to Plex automatically — with no manual file management.

### How the pieces fit together

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

### What each service does

| Service | Role |
|---------|------|
| **Plex** | Media server — streams your library to phones, TVs, browsers, Plex app |
| **Sonarr** | TV show automation — monitors for new episodes, triggers downloads, imports |
| **Radarr** | Movie automation — same as Sonarr but for movies |
| **Lidarr** | Music automation — same pattern, for albums and tracks |
| **Prowlarr** | Indexer manager — connects to torrent/usenet sites, syncs them to Sonarr/Radarr/Lidarr |
| **Bazarr** | Subtitle automation — fetches subtitles for anything Sonarr/Radarr imports |
| **qBittorrent** | Torrent client — all traffic routes through Gluetun VPN |
| **SABnzbd** | Usenet client — downloads from usenet providers |
| **Gluetun** | VPN gateway — qBittorrent's network runs entirely inside it (kill-switch) |
| **Seerr** | Request portal — lets other people request movies/shows via a clean UI |
| **Tautulli** | Plex analytics — watch history, stream stats, notifications |
| **Recyclarr** | Quality profiles — auto-syncs TRaSH Guide best-practice profiles into Sonarr/Radarr |
| **Unpackerr** | Extraction — watches for completed downloads and unpacks archives for import |

### The key ideas

**Hardlinks** — downloads and media live under the same `/data` mount. When Sonarr/Radarr import a file, they create a hardlink rather than copying it. The file exists in two places on the filesystem but uses disk space only once. qBittorrent keeps seeding the original; Plex reads the media copy. When you eventually remove the torrent, the media copy stays untouched.

**VPN kill-switch** — qBittorrent doesn't have its own network. It runs inside Gluetun's network namespace, so if the VPN drops, qBittorrent loses connectivity entirely rather than falling back to your real IP.

**Internal hostnames** — all containers share a Docker bridge network. They talk to each other by name (`http://sonarr:8989`, `http://radarr:7878`, etc.) rather than hardcoded IPs. No port forwarding or static IPs needed between services.

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [What's changed from the old setup](#whats-changed-from-the-old-setup)
- [Scripts included](#scripts-included)
- [What you need to do manually](#what-you-need-to-do-manually)
- [How downloads and seeding work](#how-downloads-and-seeding-work-with-this-setup)
- [Step 1: Copy all files to the NAS](#step-1-copy-all-files-to-the-nas)
- [Step 2: Fill in the .env file](#step-2-fill-in-the-env-file)
- [Step 3: Run setup.sh](#step-3-run-setupsh)
- [Step 4: Install the firewall script to survive reboots](#step-4-install-the-firewall-script-to-survive-reboots)
- [Step 5: Migrate Plex data from native app](#step-5-migrate-plex-data-from-native-app)
- [Step 6: Get a Plex claim token](#step-6-get-a-plex-claim-token)
- [Step 7: Start everything](#step-7-start-everything)
- [Step 8: Verify all services load](#step-8-verify-all-services-load)
- [Step 9: Update paths in all services](#step-9-update-paths-in-all-services)
- [Step 10: Configure qBittorrent seeding behavior](#step-10-configure-qbittorrent-seeding-behavior)
- [Step 11: Set up Prowlarr](#step-11-set-up-prowlarr-replaces-jackett)
- [Step 12: Clean up old Jackett indexers](#step-12-clean-up-old-jackett-indexers)
- [Step 13: Set up new services](#step-13-set-up-new-services)
- [Step 14: Test end-to-end](#step-14-test-end-to-end)
- [Troubleshooting](#troubleshooting)
- [Quick Reference](#quick-reference)

---

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

## Scripts included

All files that need to be deployed to the NAS live in the `nas/` folder.

| File | What it does |
|------|-------------|
| `docker-compose.yml` | The full stack definition |
| `.env` | Your local config and secrets — never committed to git |
| `setup.sh` | Master script — runs all setup steps below in order |
| `setup-chmod.sh` | Sets correct permissions on all stack files |
| `setup-folders.sh` | Creates all required directories and sets correct ownership |
| `setup-firewall.sh` | Applies iptables firewall rules for the stack |
| `setup-nordvpn.sh` | Fetches NordVPN WireGuard key and writes it to .env |
| `setup-validate.sh` | Validates everything is configured correctly before starting |
| `post-deploy-validate.sh` | Validates the stack is working after docker-compose up |

Run `setup.sh` once after copying files to the NAS. It handles everything in one go.

## What you need to do manually

Most of this stack is automated, but some things require human action. Here's everything that can't be scripted:

### Before first boot
- [ ] Get your NordVPN WireGuard private key (see below)
- [ ] Get a Plex claim token from https://plex.tv/claim (wait until right before `docker-compose up`)
- [ ] Copy all repo files to the NAS (Step 1)
- [ ] Fill in the `.env` file with all values (Step 2)
- [ ] Run `setup.sh` to create folders, set permissions, apply firewall rules, and install them to survive reboots (Steps 3–4)
- [ ] Migrate Plex data from the native package (Step 5)

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

## Step 1: Copy all files to the NAS

Everything that needs to be deployed lives in the `nas/` folder. Copy its contents to `/volume1/docker/media/` on the NAS.

Via SMB — open `\\192.168.1.242` in File Explorer, navigate to `docker/media`, drag the contents of the `nas/` folder in.

Or via SCP:
```bash
scp nas/* nas/.env user@192.168.1.242:/volume1/docker/media/
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
VPN_PROVIDER=nordvpn
VPN_TYPE=wireguard
NORDVPN_PRIVATE_KEY=       # from my.nordaccount.com → NordVPN → Manual config → WireGuard
VPN_COUNTRIES=             # e.g. United States, Netherlands, Switzerland
```

Save and exit (`Ctrl+X`, `Y`, `Enter`).

## Step 3: Run setup.sh

This creates all directories, sets correct ownership, and applies firewall rules:
```bash
sudo bash /volume1/docker/media/setup.sh
```

Each step prints `Created` or `Exists` for every folder, then confirms the firewall rules are applied. Safe to re-run at any time.

## Step 4: Install the firewall script to survive reboots

This is handled automatically by `setup.sh` — when `setup-firewall.sh` applies iptables rules, it also copies itself to `/usr/local/etc/rc.d/media-firewall.sh` so Synology re-applies the rules on every boot. No manual action needed.

If you ever update `setup-firewall.sh`, just re-run `setup.sh` (or `sudo bash setup-firewall.sh` directly) and it will copy the new version to rc.d automatically.

## Step 5: Migrate Plex data from native app

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

Open each service in your browser using the URLs in the Quick Reference section at the bottom of this guide. Recyclarr and Unpackerr have no web UI — they run silently in the background.

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
hostname from the internal hostnames table below.

---

## Quick Reference

### Docker Compose Cheatsheet

All commands run from `/volume1/docker/media` (the directory containing `docker-compose.yml`).

**Everyday**
```bash
docker-compose ps                         # Show all containers and their status
docker-compose up -d                      # Start all containers (or start any that are stopped)
docker-compose down                       # Stop and remove all containers
docker-compose restart sonarr             # Restart a single container
docker-compose stop sonarr                # Stop a single container without removing it
docker-compose start sonarr              # Start a previously stopped container
```

**Updates**
```bash
docker-compose pull                       # Download latest images for all services
docker-compose pull sonarr                # Download latest image for one service
docker-compose up -d                      # Recreate containers that have a newer image
docker-compose up -d sonarr              # Update and recreate one container only
```

**Logs**
```bash
docker-compose logs sonarr                # Show recent logs for a service
docker-compose logs -f sonarr             # Stream live logs (Ctrl+C to stop)
docker-compose logs -f sonarr radarr      # Stream logs for multiple services
docker-compose logs --tail=50 sonarr      # Show last 50 lines only
docker-compose logs -f                    # Stream logs for all services
```

**Debugging**
```bash
docker-compose exec sonarr bash          # Open a shell inside a running container
docker exec gluetun wget -qO- https://ipinfo.io   # Check Gluetun's external IP
docker stats                              # Live CPU/memory usage for all containers
docker-compose config                     # Print the resolved compose config (with .env applied)
docker inspect sonarr                     # Full container details (mounts, network, env vars)
docker system df                          # Show disk usage by images, containers, volumes
```

**Cleanup**
```bash
docker image prune                        # Remove unused images
docker image prune -a                     # Remove all images not used by a running container
docker system prune                       # Remove stopped containers, unused networks, dangling images
```

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

Use these when connecting services to each other (e.g. Sonarr → qBittorrent):

| Service      | Hostname       | Internal Port |
|--------------|----------------|---------------|
| Plex         | plex           | 32400         |
| Sonarr       | sonarr         | 8989          |
| Radarr       | radarr         | 7878          |
| Lidarr       | lidarr         | 8686          |
| Prowlarr     | prowlarr       | 9696          |
| Bazarr       | bazarr         | 6767          |
| SABnzbd      | sabnzbd        | 8080          |
| qBittorrent  | qbittorrent    | 8080          |
| Seerr        | seerr          | 5055          |
| Tautulli     | tautulli       | 8181          |
