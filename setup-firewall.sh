#!/bin/bash
# ── Synology Firewall Boot Script for Media Stack ──
#
# Install (run once):
#   sudo cp /volume1/docker/media/setup-firewall.sh /usr/local/etc/rc.d/media-firewall.sh
#   sudo chmod 755 /usr/local/etc/rc.d/media-firewall.sh
#
# Synology auto-runs scripts in /usr/local/etc/rc.d/ on every boot.
#
# Manual usage:
#   sudo /usr/local/etc/rc.d/media-firewall.sh start
#   sudo /usr/local/etc/rc.d/media-firewall.sh stop

LOCAL_SUBNET="192.168.1.0/24"

add_rules() {
    # DSM
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 5000 -j ACCEPT
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 5002 -j ACCEPT

    # SSH
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 22 -j ACCEPT

    # Plex (bridge network — port 32400 only, no discovery ports needed)
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 32400 -j ACCEPT

    # Sonarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49152 -j ACCEPT

    # Radarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49151 -j ACCEPT

    # Lidarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49154 -j ACCEPT

    # Prowlarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49150 -j ACCEPT

    # Bazarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49153 -j ACCEPT

    # SABnzbd
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49155 -j ACCEPT

    # qBittorrent (via Gluetun)
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49156 -j ACCEPT
    iptables -I INPUT -p tcp --dport 6881 -j ACCEPT
    iptables -I INPUT -p udp --dport 6881 -j ACCEPT

    # Seerr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 5056 -j ACCEPT

    # Tautulli
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 8181 -j ACCEPT
}

remove_rules() {
    # DSM
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 5000 -j ACCEPT 2>/dev/null
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 5002 -j ACCEPT 2>/dev/null

    # SSH
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 22 -j ACCEPT 2>/dev/null

    # Plex
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 32400 -j ACCEPT 2>/dev/null

    # Sonarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49152 -j ACCEPT 2>/dev/null

    # Radarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49151 -j ACCEPT 2>/dev/null

    # Lidarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49154 -j ACCEPT 2>/dev/null

    # Prowlarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49150 -j ACCEPT 2>/dev/null

    # Bazarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49153 -j ACCEPT 2>/dev/null

    # SABnzbd
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49155 -j ACCEPT 2>/dev/null

    # qBittorrent (via Gluetun)
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49156 -j ACCEPT 2>/dev/null
    iptables -D INPUT -p tcp --dport 6881 -j ACCEPT 2>/dev/null
    iptables -D INPUT -p udp --dport 6881 -j ACCEPT 2>/dev/null

    # Seerr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 5056 -j ACCEPT 2>/dev/null

    # Tautulli
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 8181 -j ACCEPT 2>/dev/null
}

case "$1" in
    stop)
        echo "Removing media stack firewall rules..."
        remove_rules
        echo "Done."
        ;;
    *)
        # Default to start (covers both explicit 'start' and boot — Synology calls without args)
        # Always remove first so re-running never creates duplicate rules
        echo "Applying media stack firewall rules..."
        remove_rules
        add_rules
        echo "Done."
        ;;
esac
