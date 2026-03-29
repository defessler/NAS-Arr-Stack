$nas = "192.168.1.242"

$services = @(
    @{ Name = "DSM";          Port = 5000  }
    @{ Name = "DSM (HTTPS)";  Port = 5001  }
    @{ Name = "Plex";         Port = 32400 }
    @{ Name = "Sonarr";       Port = 49152 }
    @{ Name = "Radarr";       Port = 49151 }
    @{ Name = "Prowlarr";     Port = 49150 }
    @{ Name = "SABnzbd";      Port = 49155 }
    @{ Name = "qBittorrent";  Port = 49156 }
    @{ Name = "Bazarr";       Port = 49153 }
    @{ Name = "Overseerr";    Port = 5055  }
    @{ Name = "Tautulli";     Port = 8181  }
    @{ Name = "SSH";          Port = 22    }
)

Write-Host "`nChecking NAS ports on $nas...`n" -ForegroundColor Cyan

foreach ($svc in $services) {
    $result = Test-NetConnection -ComputerName $nas -Port $svc.Port -WarningAction SilentlyContinue -InformationLevel Quiet
    if ($result) {
        Write-Host "  OK    " -ForegroundColor Green -NoNewline
    } else {
        Write-Host "  FAIL  " -ForegroundColor Red -NoNewline
    }
    Write-Host "$($svc.Name) (:$($svc.Port))"
}

Write-Host ""
