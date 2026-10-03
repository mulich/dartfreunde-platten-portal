# Dartfreunde Platten – Account-Zentrale

Ein lokales Portal für mehrere getrennte Autodarts-Accounts in einem Fenster.
Jeder Spieler bekommt ein eigenes Chromium-Profil auf dem Server. Das Portal
überträgt dessen Bildschirm und leitet Klicks, Tastatureingaben und Scrollen weiter.
Es ist keine Einbettung per iframe: So bleiben Cookies und Logins wirklich getrennt.

## Start auf Proxmox / Docker

Docker in einer Linux-VM auf Proxmox verwenden. Im Projektordner:

```sh
docker compose up -d --build
```

Portal unter `http://SERVER-IP:18080` direkt öffnen. Es gibt keine Portal-Passwortabfrage.
Spieler hinzufügen und in der eingebetteten Ansicht bei Autodarts anmelden.
Danach den nächsten Spieler auswählen. Die bisherigen Browser bleiben geöffnet.
Einladungen werden zunächst manuell in den Spieleransichten angenommen.

Für GitHub-Builds, fertige Container-Images und Updates mit Portainer siehe
[DEPLOYMENT.md](DEPLOYMENT.md).

## Anmeldung

Unterstützt wird die direkte Anmeldung mit Autodarts-Zugangsdaten in der
Spieleransicht. Google-Anmeldung, separate Chrome-Fenster und QR-Anmeldung
werden nicht unterstützt. Der Betrieb erfolgt über Docker bzw. Portainer;
auf dem Server ist kein Desktop erforderlich.

Bestehende Chromium-Spielersitzungen bleiben im Datenvolume erhalten. Falls ein
Spielerprofil aus der früheren Desktop-/Chrome-Variante stammt, wird daneben ein
neues Chromium-Profil angelegt. Dieser Spieler muss sich mit Autodarts-Zugangsdaten
neu anmelden; das alte Profil wird beim Update nicht gelöscht.

„Sitzung aktiv“ bedeutet Browser aktiv, nicht nachgewiesener Autodarts-Online-Status.
Die App deaktiviert Chromium-Hintergrunddrosselung; ob Autodarts die Accounts über
einen ganzen Abend als online führt, muss mit echten Accounts geprüft werden.
Der Server darf dabei nicht in den Standby gehen.

## Was gespeichert wird

`data/` enthält Spielernamen und die Browserprofile
mit Autodarts-Cookies. Beim Serverstart werden alle gespeicherten Spieler geöffnet.
Eine pausierte Sitzung wird beim nächsten Serverstart ebenfalls geöffnet.
„Entfernen“ löscht Profil und gespeicherte Anmeldung dauerhaft. Autodarts kann
Anmeldungen jederzeit selbst ablaufen lassen und erneute Anmeldung verlangen.
Das Portal hat kein Formular zum Sammeln von Autodarts-Passwörtern. Eingaben in
die Autodarts-Ansicht laufen allerdings durch den Portalserver; dessen Betreiber
muss vertrauenswürdig sein. Das Portal ist für euer eigenes VLAN eingerichtet und
benötigt keine Portal-Anmeldung. Die gespeicherten Autodarts-Anmeldungen bleiben erhalten.

## Lokaler Start ohne Docker

Python 3.11 oder neuer:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH="$PWD/data/browsers" .venv/bin/playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$PWD/data/browsers" .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Docker enthält bereits den passenden Browser.

## Umfang und Grenzen

- Eigene Sitzung je Spieler, Anmeldung und manuelle Einladungsannahme in einem Tab.
- Wechseln, pausieren, erneut öffnen, löschen und Wiederherstellen nach Serverstart.
- Tastatureingabe und Einfügen aus der Zwischenablage; mobile Texteingabe unter der Ansicht.
- Automatische Einladungsannahme pro Spieler; kein Turnierplaner in dieser Version.
- Eine Autodarts-Anmeldung ist nicht gleichzeitiges Spielen an mehreren Boards.
  Jeder Spieler sollte nur seiner aktuellen Begegnung beitreten.
- Zuordnung zum Gastgeber-Board und persönliche Statistik müssen mit echten Matches
  geprüft werden. Das Portal verändert weder Lobbydaten noch Boardauswahl.
- Passkeys, Hardware-Sicherheitsschlüssel, Downloads und Datei-Uploads sind durch
  die Bildschirmfernsteuerung nicht unterstützt. Passwortbasierte Anmeldung und
  per Tastatur eingegebene Bestätigungscodes sind vorgesehen.
- Keine Profilbilder oder Online-Anzeigen erfunden: Das Portal kennt nur den
  Browserzustand; die echten Informationen stehen in der Autodarts-Ansicht.

Pro Account läuft ein eigener Browserprozess. Für den ersten Test mit zwei Spielern
beginnen und RAM/CPU beobachten, anschließend weitere Accounts hinzufügen.
Mehrere Portalnutzer können dieselbe Sitzung bedienen; für Turniere einen Bediener
verwenden. Die Automatik nimmt ausschließlich Einladungen der freigegebenen Board-Accounts an.

## Tests

```sh
.venv/bin/pip install pytest httpx
.venv/bin/python -m pytest -q
```

Die automatischen Tests prüfen direkten Portalzugriff, getrennte Profilverzeichnisse,
Persistenz und Bildschirmsteuerung mit einem simulierten Browser. Sie ersetzen
keinen Login-/Lobby-Test bei Autodarts.

## Automatische Einladungsannahme

Unter „Erlaubte Board-Accounts“ stehen zunächst `rot`, `schwarz` und `blau`.
Die Schreibweise muss dem tatsächlichen Autodarts-Absender entsprechen; Groß- und
Kleinschreibung wird ignoriert. Alternativ können dort eindeutige User-IDs stehen.
Spieler auswählen und „Lobby-Einladungen automatisch annehmen“ einschalten.
Die Einstellung bleibt nach Neustarts erhalten. Anfangs ist sie aus.

Der Server prüft alle Spieler alle zwei Sekunden, unabhängig davon, welche Ansicht
im Portal ausgewählt ist. Er liest die Notification-Daten der aktuellen Autodarts-
Oberfläche und klickt deren normalen Accept-/Join-Knopf. Freundesanfragen und
Turniereinladungen werden nicht angenommen. Ohne erlaubte Absender wird nichts
angenommen. Ein bestätigter Wechsel in die Ziellobby wird mit Uhrzeit angezeigt.
Fehlgeschlagene Beitritte werden höchstens dreimal versucht, mit mindestens 30 Sekunden
Abstand. Aus- und Einschalten erlaubt einen erneuten Versuch.

In einer Lobby oder einem noch laufenden Match wartet die Automatik. Im Match muss
Autodarts den Abschluss im Spielzustand melden; ein unbekannter Zustand blockiert
die Annahme. Zum Wechsel aus einer verlassenen Lobby ggf. „Autodarts öffnen“ drücken.
Beim Aktivieren öffnet die Automatik bei Bedarf einmal den Notification-Bereich,
um noch ungelesene Einladungen zu finden. Die browserinterne React-Datenstruktur
ist keine garantierte öffentliche Schnittstelle und kann sich bei Autodarts-Updates
ändern. Dann bleibt die manuelle Annahme möglich.

Validiert mit Tests und Browserfixtures anhand der öffentlichen Autodarts-Webversion
vom 03.10.2026. Ein echter Eingang einer Einladung von euren Board-Accounts muss
anschließend vor Ort geprüft werden. Das Portal startet keine Spiele automatisch.
