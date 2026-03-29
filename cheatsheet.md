# Docker Compose Cheatsheet

All commands run from the directory containing `docker-compose.yml`

```bash
docker-compose up -d              # Start all containers
docker-compose down               # Stop all containers
docker-compose pull               # Download latest images
docker-compose up -d              # Apply updates after pulling
docker-compose logs -f sonarr     # Watch logs for one service
docker-compose restart sonarr     # Restart one service
docker-compose ps                 # See what's running
```

# Service URLs

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

# Internal Hostnames (for connecting services to each other)

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
