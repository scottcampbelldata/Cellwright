# Cellwright: Schnellstart

Der Cellwright-Scanner inventarisiert Arbeitsmappen offline, ohne Makros auszuführen oder Quelldateien zu verändern. Er benötigt weder Office noch Python. Die optionalen Konvertierungswerkzeuge und das Dashboard benötigen Python, UNO-Ziele zusätzlich LibreOffice.

```powershell
cellwright.exe scan C:\Finance --out .\berichte\finance --lang de --no-source
cellwright.exe extract .\Budget.xlsm --out .\berichte\quelltext --lang de
cellwright.exe rules list --lang de
```

Das Zielverzeichnis muss neu oder leer sein. Der HTML-Bericht funktioniert offline und bietet Suche und Sortierung. CSV-Dateien und `scan.json` ermöglichen weitere Auswertungen. `extract` exportiert VBA-Code und M-Abschnitte mit Herkunftsmanifest. `.frm`-Dateien enthalten keinen Formulardesigner.

`--no-source` lässt VBA- und M-Quelltext weg; Pfade, Namen, Referenzen und Befunde bleiben sichtbar. `--skip-protected` überspringt geschütztes VBA und unbekannte Schutzstatus. Verschlüsselte Dateien werden nicht entschlüsselt. Exit-Code `1` meldet eine unvollständige Prüfung, `2` einen Konfigurations- oder Ausgabefehler.

Aufwandsschätzungen sind unkalibrierte Annahmen. Die Bewertung „Keine bekannten Hindernisse“ belegt keine LibreOffice-Kompatibilität. XLS/XLSB-Funktionen werden teilweise erfasst; lesbare UserForm-Steuerelemente werden inventarisiert, der Designer aber nicht konvertiert. Quelltext/Cache-Abweichungen sind Hinweise, keine vollständige VBA-Stomping-Erkennung.

```powershell
cellwright.exe serve --port 8768
cellwright.exe convert .\Budget.xlsm --out .\kandidat --target basic
cellwright.exe migrate verify .\fall.json --out .\nachweis --allow-execution
```

Unter http://127.0.0.1:8768 stehen Verlauf, Zuständigkeiten, Status und geplante Scans bereit, solange der Server läuft. Konvertierung bewahrt Originale, Unterschiede und TODOs. Ausführung ist ausdrücklich freizugeben und nur für vertrauenswürdigen Code vorgesehen; sie ist nicht vom Betriebssystem isoliert. Ein erfolgreicher Fall belegt nur die verglichenen Eingaben/Zellen. Python- und M/pandas-Ziele unterstützen den in `docs/migration.md` beschriebenen Teilumfang.

Die Sprachauswahl bietet **English, Français und Deutsch** für die Oberfläche, Befunde sowie die Anzeige von Datums- und Zahlenwerten. Beim ersten Aufruf wird eine unterstützte Browsersprache verwendet, andernfalls Englisch. Der Browser merkt sich Ihre Auswahl; die Übersetzungen funktionieren offline. Neue Scans und geplante Scans übernehmen diese Sprache zunächst als Berichtssprache, die Sie separat ändern können. Jeder Zeitplan behält seine Berichtssprache; bestehende Zeitpläne verwenden weiterhin Englisch. Bereits exportierte Berichte behalten ihre Sprache.

Diese Funktion ist im aktuellen Quellcode enthalten; veröffentlichte Archive müssen dafür neu erstellt werden. Die Sprache der Oberfläche ändert nicht die Konvertierungsregeln für Tabellen: M-Kulturen außerhalb von `en-US` und `en-GB` erfordern manuelle Anpassung, und UNO-Zahlenformate verwenden `en-US`. Technische Diagnosemeldungen können weiterhin auf Englisch erscheinen. Siehe [Übersetzungsumfang](../localization.md).

Zum Kompilieren: Rust 1.99.0 und `cargo build --locked --release`. TOML-Beispiele für Regeln und Gewichtungen stehen in `data/`. Vollständige Optionen und Grenzen sind im englischen README dokumentiert. Diese Übersetzung wurde nicht von Muttersprachlern geprüft.
