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

    # Plex
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 32400 -j ACCEPT
    iptables -I INPUT -s $LOCAL_SUBNET -p udp --dport 1900 -j ACCEPT
    iptables -I INPUT -s $LOCAL_SUBNET -p udp --dport 5353 -j ACCEPT
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 8324 -j ACCEPT
    iptables -I INPUT -s $LOCAL_SUBNET -p udp --dport 32410:32414 -j ACCEPT
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 32469 -j ACCEPT

    # Sonarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49152 -j ACCEPT

    # Radarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49151 -j ACCEPT

    # Prowlarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49150 -j ACCEPT

    # Bazarr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49153 -j ACCEPT

    # SABnzbd
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49155 -j ACCEPT

    # qBittorrent
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 49156 -j ACCEPT
    iptables -I INPUT -p tcp --dport 6881 -j ACCEPT
    iptables -I INPUT -p udp --dport 6881 -j ACCEPT

    # Overseerr
    iptables -I INPUT -s $LOCAL_SUBNET -p tcp --dport 5055 -j ACCEPT

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
    iptables -D INPUT -s $LOCAL_SUBNET -p udp --dport 1900 -j ACCEPT 2>/dev/null
    iptables -D INPUT -s $LOCAL_SUBNET -p udp --dport 5353 -j ACCEPT 2>/dev/null
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 8324 -j ACCEPT 2>/dev/null
    iptables -D INPUT -s $LOCAL_SUBNET -p udp --dport 32410:32414 -j ACCEPT 2>/dev/null
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 32469 -j ACCEPT 2>/dev/null

    # Sonarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49152 -j ACCEPT 2>/dev/null

    # Radarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49151 -j ACCEPT 2>/dev/null

    # Prowlarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49150 -j ACCEPT 2>/dev/null

    # Bazarr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49153 -j ACCEPT 2>/dev/null

    # SABnzbd
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49155 -j ACCEPT 2>/dev/null

    # qBittorrent
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 49156 -j ACCEPT 2>/dev/null
    iptables -D INPUT -p tcp --dport 6881 -j ACCEPT 2>/dev/null
    iptables -D INPUT -p udp --dport 6881 -j ACCEPT 2>/dev/null

    # Overseerr
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 5055 -j ACCEPT 2>/dev/null

    # Tautulli
    iptables -D INPUT -s $LOCAL_SUBNET -p tcp --dport 8181 -j ACCEPT 2>/dev/null
}

case "$1" in
    start)
        echo "Adding media stack firewall rules..."
        add_rules
        echo "Done."
        ;;
    stop)
        echo "Removing media stack firewall rules..."
        remove_rules
        echo "Done."
        ;;
    *)
        # Default to start (Synology calls scripts without arguments on boot)
        echo "Adding media stack firewall rules..."
        add_rules
        echo "Done."
        ;;
esac
