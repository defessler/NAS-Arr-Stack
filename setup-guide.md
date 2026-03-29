# NAS Media Stack Setup Guide

## Prerequisites
- New DS1522+ with DSM installed
- All media files already at `/volume1/Data/Media/`
- All config folders already at `/volume1/docker/media/`
- Container Manager (Docker) installed from Package Center

## What's changed from the old setup
- **Plex** moved from native Synology package to Docker (portable, easier updates)
- **Jackett** replaced by **Prowlarr** (auto-syncs indexers to Sonarr/Radarr)
- **Overseerr** added (lets users request media via a clean web UI)
- **Tautulli** added (Plex stats and monitoring)
- **All containers** on a shared Docker network (talk to each other by name, no hardcoded IPs)
- **Unified `/data` mount** across all containers (enables hardlinks — no more doubled disk usage on imports)
- **PUID/PGID standardized** to 1034/100 across all containers (was inconsistent before)
- **API keys** moved to `.env` file (no longer hardcoded in docker run commands)

## How downloads and seeding work with this setup

```
1. Sonarr/Radarr send a download to qBittorrent or SABnzbd
2. Download goes to /data/Downloads/Torrents/InProgress/ (or /data/Downloads/Usenet/)
3. When complete, Sonarr/Radarr create a HARDLINK in /data/Media/
   - Same file, two paths, NO extra disk space used
   - The original stays in the download folder for seeding
4. qBittorrent keeps seeding from the original path
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

## Step 2: Create config folders for new services

SSH into the NAS and run:
```bash
mkdir -p /volume1/docker/media/plex/config \
         /volume1/docker/media/prowlarr/config \
         /volume1/docker/media/qbittorrent/config \
         /volume1/docker/media/tautulli/config \
         /volume1/docker/media/overseerr/config \
         /volume1/docker/media/sabnzbd/config \
         /volume1/docker/media/unpackerr/config \
         /volume1/docker/media/radarr/config \
         /volume1/docker/media/sonarr/config \
         /volume1/docker/media/bazarr/config

```
Existing service configs (sonarr, radarr, sabnzbd, bazarr, unpackerr) are already in place from the migration.

## Step 3: Migrate Plex data from native app

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

## Step 4: Fix file permissions

The old setup used inconsistent user IDs. The new setup standardizes to 1034/100:
```bash
chown -R 1034:100 /volume1/docker/media/sabnzbd
chown -R 1034:100 /volume1/Data/Downloads/Usenet
```

## Step 5: Get a Plex claim token

1. Go to https://plex.tv/claim
2. Copy the token (starts with `claim-`)
3. Edit the `.env` file on the NAS:
```bash
nano /volume1/docker/media/.env
```
4. Paste the token on the `PLEX_CLAIM=` line
5. Save and exit (`Ctrl+X`, `Y`, `Enter`)

**The token expires in 4 minutes — do this right before Step 6.**

## Step 6: Start everything

```bash
cd /volume1/docker/media
docker-compose up -d
```
First run takes a few minutes to download all images. Watch progress with:
```bash
docker-compose logs -f
```
Press `Ctrl+C` to stop watching logs (containers keep running).

## Step 7: Verify all services load

**Expected:** Sonarr and Radarr will show warnings about missing root folders
(`/tv/shows`, `/movies`, etc.). This is normal — the old mount paths don't exist
anymore. You'll fix this in Step 8.

Open each in your browser:

| Service      | URL                              |
|--------------|----------------------------------|
| Plex         | http://192.168.1.242:32400/web   |
| Sonarr       | http://192.168.1.242:49152       |
| Radarr       | http://192.168.1.242:49151       |
| Prowlarr     | http://192.168.1.242:49150       |
| SABnzbd      | http://192.168.1.242:49155       |
| qBittorrent  | http://192.168.1.242:49156       |
| Bazarr       | http://192.168.1.242:49153       |
| Overseerr    | http://192.168.1.242:5055        |
| Tautulli     | http://192.168.1.242:8181        |

## Step 8: Update paths in all services

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

## Step 9: Configure qBittorrent seeding behavior

In qBittorrent (http://192.168.1.242:49156):
- Settings → BitTorrent → Seeding Limits: set your preferred ratio (e.g., 2.0) or time limit
- Do NOT enable "When ratio is reached → Remove torrent" unless you want automatic cleanup
- Sonarr/Radarr will not delete the download while qBittorrent is still seeding

## Step 10: Set up Prowlarr (replaces Jackett)

1. Open Prowlarr at http://192.168.1.242:49150
2. Settings → Apps → add **Sonarr**:
   - Prowlarr Server = `http://prowlarr:9696`
   - Sonarr Server = `http://sonarr:8989`
   - API Key = `de80965dba6343b19af62770a1f05eff`
3. Settings → Apps → add **Radarr**:
   - Prowlarr Server = `http://prowlarr:9696`
   - Radarr Server = `http://radarr:7878`
   - API Key = `6442cee7ec7141d79c9e18e687b8ab1c`
4. Indexers → add your indexers (same ones you had in Jackett)
5. Prowlarr automatically syncs them to Sonarr and Radarr

## Step 11: Clean up old Jackett indexers

In both **Sonarr** and **Radarr** → Settings → Indexers:
Delete all old Jackett-based indexers. Prowlarr has already synced its own.

## Step 12: Set up new services

### Overseerr (http://192.168.1.242:5055)
1. First launch walks you through setup
2. Connect to Plex: use `http://192.168.1.242:32400`
3. Connect to Sonarr: use `http://sonarr:8989` + API key
4. Connect to Radarr: use `http://radarr:7878` + API key
5. Share the URL with anyone you want to let request movies/shows

### Tautulli (http://192.168.1.242:8181)
1. First launch walks you through setup
2. Connect to Plex: use `http://192.168.1.242:32400`

## Step 13: Test end-to-end

1. Search for something in Sonarr or Radarr
2. Trigger a manual download via torrent — verify:
   - qBittorrent downloads to `/data/Downloads/Torrents/InProgress/`
   - Sonarr/Radarr imports it to `/data/Media/`
   - qBittorrent keeps seeding after import
   - Check Sonarr/Radarr activity log says "hardlinked" (not "copied")
3. Trigger a manual download via usenet — verify SABnzbd + import works
4. Check Plex sees newly imported media
5. Try requesting something through Overseerr

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

**Sonarr/Radarr shows missing root folder errors?**
Expected on first boot. Follow Step 8 to add new root folders and reassign.

**Sonarr/Radarr says "copied" instead of "hardlinked"?**
- Verify "Use Hardlinks instead of Copy" is enabled in Settings → Media Management
- This should work because downloads and media are both under the single `/data` mount

**Sonarr/Radarr can't find downloads?**
Old paths like `/downloads` or `/Downloads/complete` no longer exist.
Download paths are now under `/data/Downloads/`. Update the download client config in Step 8.

**Torrents stop seeding after import?**
In Sonarr/Radarr → Settings → Download Clients:
- "Completed Download Handling → Remove" should be set to a condition you're comfortable with
  (e.g., after reaching seed ratio), or set to "Never" and manage cleanup in qBittorrent

**Bazarr can't find media files?**
Delete any old path mappings that reference `/_video`. Bazarr now shares the
same `/data` mount as Sonarr/Radarr — paths match automatically.

**Old NAS IP references lingering?**
Search each service's settings for `192.168.1.241` and replace with the container
hostname from the cheatsheet.
