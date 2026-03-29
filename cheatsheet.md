# Docker Compose Cheatsheet

All commands run from `/volume1/docker/media`

```bash
docker-compose up -d          # Start all containers
docker-compose down            # Stop all containers
docker-compose pull            # Download latest images
docker-compose up -d           # Apply updates after pulling
docker-compose logs -f sonarr  # Watch logs for one service
docker-compose restart sonarr  # Restart one service
docker-compose ps              # See what's running
```

# Service URLs

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

# Internal Hostnames (for connecting services to each other)

| Service      | Hostname       | Internal Port |
|--------------|----------------|---------------|
| Sonarr       | sonarr         | 8989          |
| Radarr       | radarr         | 7878          |
| Prowlarr     | prowlarr       | 9696          |
| SABnzbd      | sabnzbd        | 8080          |
| qBittorrent  | qbittorrent    | 8080          |
| Bazarr       | bazarr         | 6767          |
| Overseerr    | overseerr      | 5055          |
| Tautulli     | tautulli       | 8181          |
| Plex         | 192.168.1.242  | 32400         |
