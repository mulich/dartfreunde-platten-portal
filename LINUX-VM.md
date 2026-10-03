# Linux-VM auf Proxmox

Diese Variante läuft direkt in einer Linux-VM mit Desktop, ohne Docker.
Das Portal bleibt von anderen Rechnern unter `http://VM-IP:18080` erreichbar.
Die Google-Anmeldung öffnet normales Chrome auf dem **Desktop der VM**.
Du bedienst dieses Fenster über die Proxmox-Konsole. Es wird nicht im Portal
auf dem Handy oder im Browser des anderen PCs angezeigt.

## 1. VM vorbereiten

Als Ausgangspunkt Ubuntu Desktop 24.04 LTS (AMD64) installieren. Für einen ersten
Test mit wenigen Spielern 4 virtuelle CPUs, 8 GB RAM und 32 GB Disk vorsehen;
bei mehr Spielern den Verbrauch beobachten. Die Netzwerkkarte an eure Bridge
bzw. das Portal-VLAN anschließen und der VM eine feste Adresse oder DHCP-Reservierung
geben. Die Desktop-Ausgabe muss in der Proxmox-Konsole sichtbar sein.

Einen normalen Benutzer, z. B. `dartportal`, anlegen und am Desktop anmelden.
Das Portal und Chrome müssen unter diesem selben Benutzer laufen.
Den automatischen Ruhezustand in den Energieeinstellungen abschalten.
Für Start nach einem VM-Neustart entweder diesen Benutzer am Desktop anmelden
oder bewusst die automatische Desktop-Anmeldung in Ubuntu konfigurieren.
Ein SSH-Login allein reicht nicht. Der Dienst wird beim Desktop-Login gestartet.

## 2. Projekt und Browser installieren

Im Terminal **innerhalb des VM-Desktops**:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/mulich/dartfreunde-platten-portal.git
cd dartfreunde-platten-portal
bash scripts/install-linux.sh 18080
```

Das Repository ist privat: Für das Klonen GitHub-Zugang mit Lesezugriff verwenden.
Das öffentliche Container-Image wird bei dieser Installation nicht gebraucht.
Falls du das Projekt als ZIP herunterlädst, gilt der gleiche Installationsbefehl;
für Updates musst du dann eine neue ZIP-Version entpacken und `data/` bewahren.

Das Skript installiert Python, Playwright-Abhängigkeiten, Chromium und, falls
noch nicht vorhanden, Google Chrome vom offiziellen Google-Downloadserver.
Es legt einen systemd-Benutzerdienst sowie einen Desktop-Autostart an und startet
das Portal auf Port **18080**. Es benötigt für Systempakete dein sudo-Passwort.
Bei aktivierter VM-Firewall diesen TCP-Port für das eigene VLAN freigeben.

## 3. Spieler mit Google anmelden

1. `http://VM-IP:18080` öffnen und einen Spieler hinzufügen bzw. auswählen.
2. **Google-Anmeldung in Chrome** anklicken.
3. Zur Proxmox-Konsole wechseln. Dort öffnet sich das Chrome-Fenster dieses Spielers.
4. Bei Autodarts anmelden, bis die Autodarts-Seite angemeldet angezeigt wird.
5. Alle Chrome-Fenster dieses Spielerprofils schließen. Chrome darf für dieses
   Profil nicht weiter im Hintergrund laufen.
6. Im Portal **Anmeldung übernehmen** anklicken.
7. Für weitere Spieler wiederholen. Jeder erhält ein eigenes Profil.
8. Pro Spieler die automatische Einladungsannahme einschalten; die erlaubten
   Board-Absender `rot`, `schwarz`, `blau` überprüfen und eine echte Einladung testen.

Chrome wird für die Anmeldung ohne Automatisierungs- oder Debugging-Schalter
gestartet. Hintergrundbetrieb ist für diese Fenster deaktiviert, damit das Profil
nach dem Schließen übernommen werden kann. Ob Google die Anmeldung in eurer VM
akzeptiert, muss mit einem echten Account getestet werden.
macOS-Profile und Container-Profile nicht als portable Google-Anmeldungen kopieren;
in der VM neu anmelden. Die Browserprofile bleiben in `data/` auf der VM.

## Betrieb und Updates

Status und Logs (als derselbe Desktop-Benutzer):

```bash
systemctl --user status dartfreunde-portal.service
journalctl --user -u dartfreunde-portal.service -n 100 --no-pager
```

Neustart im Desktop-Terminal:

```bash
bash scripts/start-linux-desktop.sh
```

Update im Projektordner, nachdem alle Google-Anmeldefenster geschlossen sind:

```bash
systemctl --user stop dartfreunde-portal.service
git pull --ff-only
bash scripts/install-linux.sh 18080
```

`data/` bleibt erhalten. Ein Neustart unterbricht die Browser-Sitzungen kurz;
Updates zwischen den Turnieren durchführen. Für ein konsistentes Backup den Dienst
stoppen, alle Anmeldefenster schließen und dann `data/` sichern.
Abmelden vom VM-Desktop kann den Dienst beenden; zum Spielen angemeldet bleiben.
Eine Bildschirmsperre meldet den Benutzer nicht ab, muss zur Login-Bedienung aber
entsperrt werden. Die Proxmox-Konsole dient nur der Anmeldung; während des Turniers
werden Spieler und Einladungen über das Portal bedient.
