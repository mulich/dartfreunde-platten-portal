# GitHub, Docker Compose und Portainer

## Updates aus dem Quellcode

Auf dem Docker-Rechner das private Repository
`https://github.com/mulich/dartfreunde-platten-portal` klonen, dann im Projektordner:

```sh
docker compose up -d --build
```

Für spätere Änderungen:

```sh
git pull --ff-only
docker compose up -d --build
```

Diese Variante verwendet `compose.yaml` und bewahrt die Spielersitzungen in `./data`.
Die Daten sind vom Quellcode getrennt und werden nicht auf GitHub hochgeladen.

## Fertige Images aus GitHub

GitHub Actions prüft bei jedem Push auf `main` oder `master` die Tests und baut
anschließend das Docker-Image in GHCR. Pushes auf den Standardbranch aktualisieren
den Tag `latest`. Jeder Build hat zusätzlich einen unveränderlich benannten
`sha-<Commit-ID>`-Tag. Versions-Tags wie `v1.0.0` erzeugen den Image-Tag `1.0.0`.
Der Build ist für Linux/amd64 vorgesehen (typische Proxmox-PCs).

Nach dem ersten erfolgreichen Build lautet der Image-Name:

```text
ghcr.io/mulich/dartfreunde-platten-portal:latest
```

Das Package ist bei der ersten
Veröffentlichung normalerweise privat. Für ein privates Image im Docker-Rechner
mit einem GitHub-Zugang mit `read:packages` anmelden. Tokens nicht im Compose-Code
ablegen. Alternativ kann der Eigentümer das Container-Package öffentlich freigeben.

### Docker Compose mit fertigem Image

Das Standardimage ist bereits hinterlegt. Optional `PORTAL_IMAGE` auf einen bestimmten Versions-Tag setzen:

```sh
export PORTAL_IMAGE=ghcr.io/mulich/dartfreunde-platten-portal:latest
docker compose -f compose.portainer.yaml pull
docker compose -f compose.portainer.yaml up -d
```

Bei späteren Updates die letzten zwei Befehle erneut ausführen. Diese Variante
verwendet das benannte Volume `dartfreunde-platten-portal-data`. Quellcode-Bind-Mount
und benanntes Volume sind **verschiedene Datenspeicher**; beim Wechsel nicht davon
ausgehen, dass vorhandene Profile automatisch übernommen werden.

### Portainer

1. Bei einem privaten Image unter **Registries** GHCR (`ghcr.io`) mit einem
   berechtigten GitHub-Zugang hinzufügen.
2. Unter **Stacks → Add stack → Repository** das Projekt-Repository auswählen.
   Für ein privates Repository zusätzlich den Repository-Zugang konfigurieren.
3. Als Compose path `compose.portainer.yaml` verwenden.
4. Das Image `ghcr.io/mulich/dartfreunde-platten-portal:latest` ist bereits
   hinterlegt. Optional `PORTAL_IMAGE` für eine feste Version oder `PORTAL_PORT`
   für einen anderen Port setzen; Standard ist `8000`.
5. Stack bereitstellen. Das Portal öffnet sich unter `http://SERVER-IP:8000`.
6. Für ein Update nach erfolgreichem GitHub-Build **Pull and redeploy** mit
   **Re-pull image** verwenden. Das Datenvolume bleibt dabei erhalten.

Alternativ den Inhalt von `compose.portainer.yaml` in den Portainer-Webeditor
kopieren. Beide Umgebungsvariablen sind optional. Automatische Updates am GitHub-Repository
allein garantieren noch kein neues Image auf dem Docker-Host; dort muss ein Pull
und Redeploy erfolgen. Ein Portainer-Webhook oder Polling kann später gezielt
konfiguriert werden.

## Zurück zur vorigen Version

`PORTAL_IMAGE` auf einen vorherigen `sha-<Commit-ID>`-Tag ändern und den Stack erneut
bereitstellen. Vor Updates das Datenvolume sichern. Gespeicherte Chrome-Profile
sind versions- und betriebssystemabhängig; ein Image-Rollback ist keine Garantie
für kompatible Profile. macOS-Profile können nicht als portable Anmeldung für
den Linux-Container vorausgesetzt werden.

## Laufender Entwicklungsprozess

Codeänderungen werden getestet und auf GitHub gepusht. Erst ein erfolgreicher
Actions-Build liefert ein neues Image. Das Portal verändert sich auf dem Server
erst nach dem gewünschten Compose-/Portainer-Update. Die lokale Entwicklungsinstanz
und der Docker-Server verwenden jeweils ihre eigenen Sitzungsdaten.
