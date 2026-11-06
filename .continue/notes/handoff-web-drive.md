# Handoff: Web-Hosting + Google Drive (Stand 2026-11-06)

Weiterarbeiten nur auf **code-server** (`/root/Private/UniDocs`).
Der fruehere Arch-Linux-PC ist ausgeschaltet und wird nicht mehr gebraucht.
Alles Noetige liegt im Repo und auf code-server.

## Schnellstart auf code-server

```bash
ssh root@code-server
cd /root/Private/UniDocs
git pull --ff-only
systemctl status unidocs-web
journalctl -u unidocs-web -f
```

Web-App: `https://code-server.tailfd3336.ts.net:8443/`
Handoff: `/root/Private/UniDocs/.continue/notes/handoff-web-drive.md`

Repo-Stand: Branch `feature/web-hosting`, Commit `49930a1`, Working Tree clean.

## Erledigt und gepusht

- Branch: `feature/web-hosting`
- Commits:
  - `ec40161 feat(web): add self-hosted web mode for iPad`
  - `30f1193 fix(web): pin FastAPI for flet-web compatibility`
- Auf code-server: gleicher Branch, Working Tree clean.
- Venv: `/root/Private/UniDocs/.venv` (Python 3.11)
- Web-Deps installiert: `pip install -e '.[web]'`
- `fastapi==0.136.0` gepinnt, weil `flet-web 0.84` mit neueren FastAPI-Versionen
  beim Start stirbt (`openapi_prefix` entfernt).
- systemd-Service:
  - Datei: `/etc/systemd/system/unidocs-web.service`
  - aktiv + enabled
  - bindet `127.0.0.1:8550`
  - Start: `/root/Private/UniDocs/.venv/bin/python tools/serve_web.py --host 127.0.0.1 --port 8550`
- Tailscale Serve:
  - `https://code-server.tailfd3336.ts.net:8443/` -> `http://127.0.0.1:8550`
  - bestehender Code-Server auf `:443` bleibt unberuehrt.
- PWA: Manifest, Icons, Titel „UniDocs“.
- `tools/serve_web.py`: `/files/...` liefert Dokumente an den Browser.
  PDF/Bilder inline, Rest als Download.
- iPad: URL in Safari oeffnen -> Teilen -> Zum Home-Bildschirm.

Nuetzliche Befehle:

```bash
systemctl status unidocs-web
systemctl restart unidocs-web
journalctl -u unidocs-web -f
```

## Google Drive: Stand

Ziel: Google Drive auf code-server mounten, UniDocs-Speicher auf den Mount.

Bereits gemacht:

- `rclone` und `fuse3` auf code-server installiert.
- rclone-Remote `gdrive:` angelegt.
  - eigener Google-OAuth-Client aus dem alten `gdrive_client_secret.json`
  - Secret liegt jetzt ausserhalb des Repos:
    `/root/.config/rclone/client_secret.json`
  - **Noch kein OAuth-Token.** `rclone listremotes` zeigt `gdrive:`, aber
    `rclone lsd gdrive:` wird erst nach Login funktionieren.
- Proxmox-LXC `101` (Code-Server) auf `pve-uw` fuer FUSE vorbereitet:
  - Backup: `/root/101.conf.bak.*`
  - ergaenzt in `/etc/pve/lxc/101.conf`:
    ```
    lxc.cgroup2.devices.allow: c 10:229 rwm
    lxc.mount.entry: /dev/fuse dev/fuse none bind,optional,create=file
    ```
  - **Noch nicht aktiv**, weil Container-Neustart fehlt.
  - `lxc-device -n 101 add /dev/fuse` schlug fehl (Hotplug geht hier nicht).

### 1. Container neu starten (FUSE aktivieren)

Auf `pve-uw`:

```bash
pct reboot 101
```

Danach pruefen:

```bash
ssh root@code-server 'ls -l /dev/fuse; systemctl is-active unidocs-web; tailscale serve status'
```

Erwartet: `/dev/fuse` existiert, `unidocs-web` active, Serve-Status unveraendert.

Falls FUSE-Eintrag Probleme macht: `/etc/pve/lxc/101.conf` aus Backup
zurueckspielen und `pct reboot 101`.

### 2. Google-Login fuer rclone

Code-Server hat keinen Browser. Es wird ein zweites Geraet mit Browser und
SSH-Client gebraucht (Laptop, iPad mit Termius/Blink, ...). Der alte Arch-PC
ist dafuer nicht noetig.

Variante A - SSH-Portweiterleitung:

```bash
ssh -L 53682:127.0.0.1:53682 root@code-server
```

Im SSH:

```bash
rclone config reconnect gdrive: --auth-no-open-browser
```

Die ausgegebene URL im Browser des zweiten Geraets oeffnen. Der Redirect geht
auf `http://127.0.0.1:53682/...`, also durch den SSH-Tunnel. Login abschliessen.
Danach:

```bash
rclone lsd gdrive:
```

Erwartet: Liste der Drive-Ordner.

Variante B - Token von einem anderen Rechner einspielen:

```bash
# auf dem Rechner mit Browser und rclone:
rclone authorize "drive" --client-id "<ID>" --client-secret "<SECRET>"
```

Den ausgegebenen Token-Block auf code-server in `rclone config` bei `gdrive:`
als `token` eintragen (`rclone config edit gdrive:`). ID/Secret stehen in
`/root/.config/rclone/rclone.conf` und `/root/.config/rclone/client_secret.json`.

### 3. Mounten

Testweise:

```bash
mkdir -p /mnt/gdrive
rclone mount gdrive: /mnt/gdrive \
  --vfs-cache-mode full \
  --dir-cache-time 5m \
  --poll-interval 30s \
  --daemon
ls /mnt/gdrive
```

Dauerhaft als systemd-Unit `/etc/systemd/system/gdrive-mount.service`:

```ini
[Unit]
Description=Google Drive via rclone
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/bin/rclone mount gdrive: /mnt/gdrive --config=/root/.config/rclone/rclone.conf --vfs-cache-mode full --vfs-cache-max-age 24h --dir-cache-time 5m --poll-interval 30s
ExecStop=/bin/fusermount3 -u /mnt/gdrive
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now gdrive-mount
systemctl status gdrive-mount
```

Falls Mount hakt: `fusermount3 -u /mnt/gdrive`, dann Service neu starten.

### 4. UniDocs auf Drive zeigen lassen

Erst pruefen, wo die Dokumente in Drive liegen:

```bash
ls -la /mnt/gdrive
```

Dann in UniDocs unter Einstellungen den Speicherordner setzen, z. B.
`/mnt/gdrive/UniDocs` (empfohlen, eigener Ordner) oder `/mnt/gdrive`, falls
die Module direkt in der Drive-Wurzel liegen.

Alternativ per Code (danach Web-Service neu starten):

```bash
cd /root/Private/UniDocs
.venv/bin/python - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "src")
from app_storage.app_config import AppConfig
AppConfig().unidocs_location = Path("/mnt/gdrive/UniDocs")
PY
systemctl restart unidocs-web
```

### 5. Testen

1. `https://code-server.tailfd3336.ts.net:8443/` im iPad-Safari.
2. Module und Dokumente sichtbar?
3. Dokument antippen: PDF/Bild inline, sonst Download.
4. Import auf dem iPad: Datei wird auf den Server hochgeladen und landet im
   Drive-Mount.
5. Nach App-Neustart: Ordner/Tags noch da?

## Wichtig / Grenzen

- Native Google Docs (Docs/Sheets/Slides) sind keine echten Dateien. rclone kann
  sie nur exportieren, nicht als Original bearbeiten. Normale PDFs/Bilder/Office-
  Dateien funktionieren.
- UniDocs schreibt Metadaten (`.meta`, `.order`, `tags.json`, `.doc_tags`) in den
  Speicherordner. Diese landen dann ebenfalls in Drive. Nicht loeschen.
- Drive-Mount ist langsamer als lokale Platte. `--vfs-cache-mode full` hilft.
- Kein Login in UniDocs. Zugriff nur ueber Tailnet + Tailscale Serve (HTTPS).
- Gleichzeitiges Bearbeiten derselben Datei auf iPad und Desktop vermeiden.
- Fallback ohne FUSE: `rclone bisync` zwischen Drive und lokalem Ordner per
  systemd-Timer. Weniger live, aber kein Container-Neustart noetig.
