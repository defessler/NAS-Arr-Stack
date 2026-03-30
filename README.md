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
- [Step 9: Run the auto-configuration script](#step-9-run-the-auto-configuration-script)
- [Step 10: Finish paths and qBittorrent setup](#step-10-finish-paths-and-qbittorrent-setup)
- [Step 11: Configure qBittorrent seeding behavior](#step-11-configure-qbittorrent-seeding-behavior)
- [Step 12: Add Prowlarr indexers](#step-12-add-prowlarr-indexers)
- [Step 13: Clean up old Jackett indexers](#step-13-clean-up-old-jackett-indexers)
- [Step 14: Finish remaining services](#step-14-finish-remaining-services)
- [Step 15: Test end-to-end](#step-15-test-end-to-end)
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
| `setup-arr-config.py` | Auto-configures all services via API after first boot |
| `fix-qbit-paths.sh` | Updates qBittorrent torrent save paths via API |

Run `setup.sh` once after copying files to the NAS. It handles everything in one go.
Then run `setup-arr-config.py` after containers are up to wire all the services together.

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
- [ ] Run `setup-arr-config.py` to auto-configure all services (Step 9)
- [ ] Reassign old root folders to new paths in Sonarr/Radarr/Lidarr Mass Editor (Step 10)
- [ ] Set qBittorrent watched folder `/downloads/ToFetch` manually in the UI (Step 10)
- [ ] Configure qBittorrent seeding limits (Step 11)
- [ ] Add your indexers in Prowlarr (Step 12) — app connections are done by the script
- [ ] Complete Seerr setup wizard, then re-run `setup-arr-config.py` to wire in Sonarr/Radarr (Step 13)
- [ ] Set up Tautulli and connect it to Plex (Step 13)
- [ ] Customise Recyclarr quality profiles (Step 13) — starter config is generated by the script
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
2. Download goes to /downloads/InProgress/ (or /data/incomplete for usenet)
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

# qBittorrent WebUI credentials — set before first boot
QBITTORRENT_USER=admin
QBITTORRENT_PASS=          # choose any password

# Gluetun VPN (NordVPN)
VPN_PROVIDER=nordvpn
VPN_TYPE=wireguard
NORDVPN_PRIVATE_KEY=       # leave blank — setup-nordvpn.sh fills this in automatically
VPN_COUNTRIES=             # e.g. United States, Netherlands, Switzerland
```

Save and exit (`Ctrl+X`, `Y`, `Enter`).

## Step 3: Run setup.sh

This runs all setup steps in order:
```bash
sudo bash /volume1/docker/media/setup.sh
```

What it does:
1. Sets correct permissions on all scripts and config files
2. Creates all required directories with correct ownership
3. Deploys the qBittorrent credential init script
4. Applies firewall rules and installs them to survive reboots
5. Fetches your NordVPN WireGuard private key and writes it to `.env`
6. Validates the full configuration

Safe to re-run at any time.

## Step 4: Install the firewall script to survive reboots

This is handled automatically by `setup.sh` — when `setup-firewall.sh` applies iptables rules, it also copies itself to `/usr/local/etc/rc.d/media-firewall.sh` so Synology re-applies the rules on every boot. No manual action needed.

If you ever update `setup-firewall.sh`, just re-run `setup.sh` (or `sudo bash setup-firewall.sh` directly) and it will copy the new version to rc.d automatically.

## Step 5: Migrate Plex data from native app

Find where the Synology Plex package stored its data:
```bash
find /volume1 -maxdepth 4 -name "Preferences.xml" -path "*/Plex*" 2>/dev/null
```

Stop the native package first:
```bash
synopkg stop PlexMediaServer
```

Copy the data into the Docker config path (the container expects this exact directory structure):
```bash
mkdir -p "/volume1/docker/media/plex/config/Library/Application Support/"

cp -a "/volume1/PlexMediaServer/Library/Application Support/Plex Media Server" \
      "/volume1/docker/media/plex/config/Library/Application Support/"
```

Fix ownership:
```bash
PUID=$(grep -m1 '^PUID=' /volume1/docker/media/.env | cut -d'=' -f2-)
PGID=$(grep -m1 '^PGID=' /volume1/docker/media/.env | cut -d'=' -f2-)
chown -R ${PUID}:${PGID} /volume1/docker/media/plex/config/
```

Adjust the source path above if your Plex data is in a different location.

> If migrating from the native package, the `PLEX_CLAIM` token in `.env` can be left blank — the existing Preferences.xml already contains your Plex account token.

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

## Step 9: Run the auto-configuration script

After all containers are up, run the configuration script to wire everything together automatically:

```bash
python3 /volume1/docker/media/setup-arr-config.py
```

**What it configures automatically:**

| Service | What gets set up |
|---|---|
| Sonarr | Root folders, qBittorrent + SABnzbd download clients, remote path mapping, hardlinks |
| Radarr | Same with `radarr` category and Movies/Anime roots |
| Lidarr | Same with `lidarr` category and Music root |
| Prowlarr | Sonarr, Radarr, and Lidarr app connections |
| SABnzbd | Incomplete/complete download directories, tv/movies/music categories |
| Bazarr | Sonarr and Radarr connections |
| Seerr | Sonarr and Radarr connections *(run after the setup wizard — see Step 14)* |
| Unpackerr | Generates `unpackerr.conf` with API keys pre-filled |
| Recyclarr | Generates starter `recyclarr.yml` with API keys pre-filled |

The script is safe to re-run — it skips anything already configured.

## Step 10: Finish paths and qBittorrent setup

Path layout inside each container:

| Service | Mount | NAS path |
|---|---|---|
| qBittorrent | `/downloads` | `/volume1/Data/Downloads/Torrents` |
| SABnzbd | `/data` | `/volume1/Data/Downloads/Usenet` |
| Sonarr / Radarr / Lidarr / Bazarr | `/data` | `/volume1/Data` |

Because qBittorrent uses `/downloads` while Sonarr/Radarr use `/data`, the script adds a **Remote Path Mapping** in each *arr automatically. Hardlinks still work — both containers read from the same physical NAS volume.

### qBittorrent — watched folder (manual step)

The watched folder can't be written by the init script. Set it manually:

Settings → Downloads → **Automatically add torrents from**: `/downloads/ToFetch`

### Sonarr — reassign existing series to new root folders

The script adds the new root folders, but existing series still point to old paths. Fix them:

1. Settings → Media Management → Root Folders → add `/data/Media/TV Shows` and `/data/Media/Anime/TV Shows` *(script does this)*
2. **Series → Mass Editor** → select all → change root folder to `/data/Media/TV Shows`
3. Repeat for anime series → `/data/Media/Anime/TV Shows`
4. Delete the old root folders once empty

### Radarr — reassign existing movies

Same pattern:
1. **Movies → Mass Editor** → select all → change root folder to `/data/Media/Movies`
2. Repeat for anime movies → `/data/Media/Anime/Movies`
3. Delete old root folders

### Bazarr — clean up old path mappings

The script connects Bazarr to Sonarr/Radarr. If you had old path mappings referencing `/_video`, delete them — Bazarr now shares the same `/data` mount as Sonarr/Radarr so paths match automatically.

## Step 11: Configure qBittorrent seeding behavior

In qBittorrent (http://192.168.1.242:49156):
- Settings → BitTorrent → Seeding Limits: set your preferred ratio (e.g., 2.0) or time limit
- Do NOT enable "When ratio is reached → Remove torrent" unless you want automatic cleanup
- Sonarr/Radarr will not delete the download while qBittorrent is still seeding

## Step 12: Add Prowlarr indexers

The script already connects Prowlarr to Sonarr, Radarr, and Lidarr. The only thing left to do manually is add your actual indexers:

1. Open Prowlarr at http://192.168.1.242:49150
2. Indexers → **+ Add Indexer** → add the same ones you had in Jackett
3. Prowlarr syncs them to Sonarr/Radarr/Lidarr automatically

## Step 13: Clean up old Jackett indexers

In **Sonarr**, **Radarr**, and **Lidarr** → Settings → Indexers:
Delete all old Jackett-based indexers. Prowlarr has already synced its own.

## Step 14: Finish remaining services

### Seerr (http://192.168.1.242:5056)

Seerr needs a setup wizard before the script can configure it:

1. Visit http://192.168.1.242:5056 and complete the wizard
2. Connect Plex during the wizard: use `http://plex:32400`
3. Re-run `setup-arr-config.py` — it will now add Sonarr and Radarr connections automatically

The script picks up quality profiles from Sonarr/Radarr automatically so you don't need to look up profile IDs.

**Migrating from Overseerr?** Seerr has a built-in migration tool under Settings → Import.

### Tautulli (http://192.168.1.242:8181)
1. First launch walks you through setup
2. Connect to Plex: use `http://plex:32400` and your Plex token
   (find your token in Plex → Settings → Troubleshooting → Get your X-Plex-Token)

### Recyclarr

The script generates a starter config at:
`/volume1/docker/media/recyclarr/config/recyclarr.yml`

It already has your Sonarr/Radarr URLs and API keys filled in. Customise it with
the TRaSH Guide quality profiles you want — see https://recyclarr.dev/wiki for full
documentation and recommended profile lists.

To trigger a manual sync after editing:
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

## Step 15: Test end-to-end

1. Verify Gluetun is connected (Step 14 above)
2. Search for something in Sonarr or Radarr
3. Trigger a manual download via torrent — verify:
   - qBittorrent downloads to `/downloads/Completed/` (via `/downloads/InProgress/` while active)
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
Library paths inside the Plex container should be:
- Movies → `/data/Media/Movies`
- TV Shows → `/data/Media/TV Shows`
- Anime Movies → `/data/Media/Anime/Movies`
- Anime TV Shows → `/data/Media/Anime/TV Shows`
- Music → `/data/Media/Music`

Update them under Settings → Libraries → Edit → Manage Folders.

**Sonarr/Radarr/Lidarr shows missing root folder errors?**
Expected on first boot. Follow Step 9 to add new root folders and reassign.

**Sonarr/Radarr says "copied" instead of "hardlinked"?**
- Verify "Use Hardlinks instead of Copy" is enabled in Settings → Media Management
- This should work because downloads and media are both under the single `/data` mount

**Sonarr/Radarr can't find downloads?**
Old paths like `/incomplete-downloads` no longer exist. Torrent downloads are under
`/downloads/` inside qBittorrent, mapped to `/data/Downloads/Torrents/` inside Sonarr/Radarr
via the remote path mapping. Usenet downloads are under `/data/incomplete` and `/data/complete`
inside SABnzbd. Re-run `setup-arr-config.py` to ensure everything is configured correctly.

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

**qBittorrent fails to start after restarting the whole stack?**
`docker-compose restart` brings all containers up simultaneously and doesn't respect dependency order —
qBittorrent tries to join Gluetun's network before Gluetun is running. Always use this instead:
```bash
docker-compose down && docker-compose up -d
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
docker-compose down && docker-compose up -d  # Restart the full stack (respects dependency order)
docker-compose restart sonarr             # Restart a single container (fine for most services)
docker-compose stop sonarr                # Stop a single container without removing it
docker-compose start sonarr               # Start a previously stopped container
```

> **Note:** Use `docker-compose down && docker-compose up -d` to restart the full stack — not `docker-compose restart`.
> `restart` brings everything back up simultaneously without respecting dependency order, which causes qBittorrent
> to fail because it tries to join Gluetun's network before Gluetun is ready. `up -d` waits for Gluetun to pass
> its healthcheck before starting qBittorrent. Restarting individual services with `restart` is fine.

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

Use these when connecting services to each other (e.g. Sonarr → qBittorrent).
`setup-arr-config.py` uses these automatically — you only need them for manual configuration.

> **qBittorrent note:** qBittorrent shares Gluetun's network namespace, so it isn't reachable by its own container name. Use `gluetun` as the hostname and `49156` as the port when adding it as a download client.

| Service      | Hostname       | Internal Port |
|--------------|----------------|---------------|
| Plex         | plex           | 32400         |
| Sonarr       | sonarr         | 8989          |
| Radarr       | radarr         | 7878          |
| Lidarr       | lidarr         | 8686          |
| Prowlarr     | prowlarr       | 9696          |
| Bazarr       | bazarr         | 6767          |
| SABnzbd      | sabnzbd        | 8080          |
| qBittorrent  | gluetun        | 49156         |
| Seerr        | seerr          | 5055          |
| Tautulli     | tautulli       | 8181          |
