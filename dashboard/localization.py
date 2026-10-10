# SPDX-License-Identifier: EUPL-1.2
"""Presentation translations; machine values and saved artifacts stay unchanged."""
import copy
import re

LANGUAGES = ("en", "fr", "de")

# shortcut: uncatalogued technical diagnostics remain in English, extend the catalog when needed in user flows.
MESSAGES = {
    "Invalid language": ("Langue non valide", "Ungültige Sprache"),
    "Job not found": ("Tâche introuvable", "Auftrag nicht gefunden"),
    "Not found": ("Introuvable", "Nicht gefunden"),
    "Invalid Host header": ("En-tête Host non valide", "Ungültiger Host-Header"),
    "Cross-origin requests are rejected": ("Les requêtes provenant d’une autre origine sont refusées", "Anfragen von einer anderen Herkunft werden abgelehnt"),
    "Invalid session token": ("Jeton de session non valide", "Ungültiges Sitzungstoken"),
    "JSON content type required": ("Le type de contenu JSON est requis", "JSON-Inhaltstyp erforderlich"),
    "Invalid request size": ("Taille de requête non valide", "Ungültige Anfragegröße"),
    "JSON object required": ("Un objet JSON est requis", "JSON-Objekt erforderlich"),
    "Invalid workbook path": ("Chemin de classeur non valide", "Ungültiger Arbeitsmappenpfad"),
    "Invalid status": ("Statut non valide", "Ungültiger Status"),
    "Assignment text too long": ("Texte d’affectation trop long", "Zuweisungstext zu lang"),
    "Interval must be 1 to 8760 hours": ("L’intervalle doit être compris entre 1 et 8 760 heures", "Das Intervall muss zwischen 1 und 8.760 Stunden liegen"),
    "Provide 1 to 100 workbook or folder paths": ("Indiquez 1 à 100 chemins de classeurs ou de dossiers", "Geben Sie 1 bis 100 Arbeitsmappen- oder Ordnerpfade an"),
    "Invalid artifact path": ("Chemin de fichier non valide", "Ungültiger Dateipfad"),
    "Artifact too large": ("Fichier trop volumineux", "Datei zu groß"),
    "Invalid target": ("Cible non valide", "Ungültiges Ziel"),
    "Select a completed conversion": ("Sélectionnez une conversion terminée", "Wählen Sie eine abgeschlossene Konvertierung"),
    "Restart the dashboard with --allow-execution to enable macro verification": ("Redémarrez le tableau de bord avec --allow-execution pour activer la vérification des macros", "Starten Sie das Dashboard mit --allow-execution neu, um die Makroprüfung zu aktivieren"),
    "Dashboard macro execution is disabled": ("L’exécution des macros est désactivée dans le tableau de bord", "Die Makroausführung im Dashboard ist deaktiviert"),
    "Explicit execution consent required": ("Une autorisation explicite d’exécution est requise", "Ausdrückliche Zustimmung zur Ausführung erforderlich"),
    "Linux verification requires a saved Excel capture JSON path": ("La vérification sous Linux nécessite le chemin d’une capture Excel enregistrée au format JSON", "Die Prüfung unter Linux benötigt den Pfad einer gespeicherten Excel-Aufnahme im JSON-Format"),
    "Saved Excel capture JSON not found": ("Capture Excel JSON enregistrée introuvable", "Gespeicherte Excel-Aufnahme im JSON-Format nicht gefunden"),
    "Standalone Python candidates use the CLI run-python and comparison tools": ("Les candidats Python autonomes utilisent les outils CLI run-python et de comparaison", "Eigenständige Python-Kandidaten verwenden die CLI-Werkzeuge run-python und zum Vergleich"),
    "Python module not found": ("Module Python introuvable", "Python-Modul nicht gefunden"),
    "Dashboard stopped before this job completed": ("Le tableau de bord s’est arrêté avant la fin de cette tâche", "Das Dashboard wurde vor Abschluss dieses Auftrags beendet"),
    "Specify 1 to 100 sheets and explicit cells to compare": ("Indiquez 1 à 100 feuilles et les cellules explicites à comparer", "Geben Sie 1 bis 100 Blätter und ausdrücklich die zu vergleichenden Zellen an"),
    "Provide sheet names and lists of explicit A1 ranges": ("Indiquez les noms des feuilles et des listes de plages A1 explicites", "Geben Sie Blattnamen und Listen expliziter A1-Bereiche an"),
    "Cell ranges must be A1 addresses": ("Les plages de cellules doivent être des adresses A1", "Zellbereiche müssen A1-Adressen sein"),
    "Snapshot exceeds 100,000 cells": ("La capture dépasse 100 000 cellules", "Die Aufnahme überschreitet 100.000 Zellen"),
    "Use a qualified procedure name without workbook or script URLs": ("Utilisez un nom de procédure qualifié sans URL de classeur ni de script", "Verwenden Sie einen qualifizierten Prozedurnamen ohne Arbeitsmappen- oder Skript-URLs"),
    "Provide up to seven scalar inputs": ("Indiquez jusqu’à sept entrées scalaires", "Geben Sie bis zu sieben skalare Eingaben an"),
    "Only finite scalar macro inputs are supported": ("Seules les entrées de macro scalaires et finies sont prises en charge", "Nur endliche skalare Makroeingaben werden unterstützt"),
    "Workbook scanner": ("Analyseur de classeurs", "Arbeitsmappen-Scanner"),
    "Inventory": ("Inventaire", "Bestandsaufnahme"),
    "Dashboard and conversion": ("Tableau de bord et conversion", "Dashboard und Konvertierung"),
    "Standalone Python workbooks": ("Classeurs Python autonomes", "Eigenständige Python-Arbeitsmappen"),
    "Power Query candidates": ("Candidats Power Query", "Power-Query-Kandidaten"),
    "Basic and UNO candidates": ("Candidats Basic et UNO", "Basic- und UNO-Kandidaten"),
    "Desktop Excel": ("Excel pour ordinateur", "Excel-Desktopanwendung"),
    "New reference captures": ("Nouvelles captures de référence", "Neue Referenzaufnahmen"),
    "Use the full Cellwright archive, or build the scanner with cargo build --locked --release.": ("Utilisez l’archive Cellwright complète ou compilez l’analyseur avec cargo build --locked --release.", "Verwenden Sie das vollständige Cellwright-Archiv oder kompilieren Sie den Scanner mit cargo build --locked --release."),
    "Install Python 3.11 or newer from python.org and add it to PATH; reopen the launcher.": ("Installez Python 3.11 ou une version ultérieure depuis python.org et ajoutez-le à PATH ; rouvrez le lanceur.", "Installieren Sie Python 3.11 oder neuer von python.org, fügen Sie es zu PATH hinzu und öffnen Sie den Starter erneut."),
    "Install the optional packages with python -m pip install -r requirements.txt.": ("Installez les paquets facultatifs avec python -m pip install -r requirements.txt.", "Installieren Sie die optionalen Pakete mit python -m pip install -r requirements.txt."),
    "On Ubuntu install python3-uno. On Windows use LibreOffice with its Python runtime; set CELLWRIGHT_UNO_PYTHON if using a separate UNO interpreter.": ("Sous Ubuntu, installez python3-uno. Sous Windows, utilisez LibreOffice avec son environnement Python ; définissez CELLWRIGHT_UNO_PYTHON si vous utilisez un interpréteur UNO distinct.", "Installieren Sie unter Ubuntu python3-uno. Verwenden Sie unter Windows LibreOffice mit seiner Python-Laufzeit; setzen Sie CELLWRIGHT_UNO_PYTHON bei einem separaten UNO-Interpreter."),
    "Install LibreOffice Calc. On Ubuntu: sudo apt install libreoffice-calc python3-uno. Set CELLWRIGHT_LIBREOFFICE to its program directory for a custom installation.": ("Installez LibreOffice Calc. Sous Ubuntu : sudo apt install libreoffice-calc python3-uno. Pour une installation personnalisée, définissez CELLWRIGHT_LIBREOFFICE sur son dossier de programme.", "Installieren Sie LibreOffice Calc. Unter Ubuntu: sudo apt install libreoffice-calc python3-uno. Setzen Sie CELLWRIGHT_LIBREOFFICE bei einer eigenen Installation auf das Programmverzeichnis."),
    "Use a saved Excel capture on Linux, or a Windows machine with Excel for new captures. Inventory and conversion do not need Excel.": ("Utilisez une capture Excel enregistrée sous Linux ou un ordinateur Windows avec Excel pour de nouvelles captures. L’inventaire et la conversion ne nécessitent pas Excel.", "Verwenden Sie unter Linux eine gespeicherte Excel-Aufnahme oder für neue Aufnahmen einen Windows-Rechner mit Excel. Bestandsaufnahme und Konvertierung benötigen kein Excel."),
    "Review the source diff. A generated candidate has not been tested.": ("Examinez les différences du code source. Un candidat généré n’a pas été testé.", "Prüfen Sie die Quellcodeänderungen. Ein erzeugter Kandidat wurde noch nicht getestet."),
    "Use the form/control recipe, review the layout and reconnect only the intended event.": ("Suivez la recette des formulaires et contrôles, examinez la disposition et reconnectez uniquement l’événement prévu.", "Verwenden Sie die Anleitung für Formulare und Steuerelemente, prüfen Sie das Layout und verbinden Sie nur das vorgesehene Ereignis erneut."),
    "Use the range recipe with explicit sheets, ranges and arguments; compare representative cells.": ("Suivez la recette des plages avec des feuilles, plages et arguments explicites ; comparez des cellules représentatives.", "Verwenden Sie die Bereichsanleitung mit expliziten Blättern, Bereichen und Argumenten; vergleichen Sie repräsentative Zellen."),
    "Review the data-source recipe and compare a saved output table before enabling refresh.": ("Examinez la recette des sources de données et comparez une table de sortie enregistrée avant d’activer l’actualisation.", "Prüfen Sie die Datenquellenanleitung und vergleichen Sie eine gespeicherte Ausgabetabelle, bevor Sie die Aktualisierung aktivieren."),
    "Replace this external dependency using the manual recipe; review permissions and side effects.": ("Remplacez cette dépendance externe à l’aide de la recette manuelle ; examinez les autorisations et les effets secondaires.", "Ersetzen Sie diese externe Abhängigkeit anhand der manuellen Anleitung; prüfen Sie Berechtigungen und Nebenwirkungen."),
    "Open the original and diff at this location, make the described edit and add a focused comparison case.": ("Ouvrez l’original et ses différences à cet emplacement, effectuez la modification décrite et ajoutez un cas de comparaison ciblé.", "Öffnen Sie Original und Änderungen an dieser Stelle, nehmen Sie die beschriebene Änderung vor und ergänzen Sie einen gezielten Vergleichsfall."),
    "Event binding generated": ("Liaison d’événement générée", "Ereignisbindung erzeugt"),
    "Inspect the saved control and compare the intended interaction.": ("Inspectez le contrôle enregistré et comparez l’interaction prévue.", "Prüfen Sie das gespeicherte Steuerelement und vergleichen Sie die vorgesehene Interaktion."),
    "Imported layout retained as an editable dialog candidate": ("Disposition importée conservée comme candidat de boîte de dialogue modifiable", "Importiertes Layout als bearbeitbarer Dialogkandidat beibehalten"),
    "Inspect positions, captions, tab order and every control before use.": ("Inspectez les positions, les libellés, l’ordre de tabulation et chaque contrôle avant utilisation.", "Prüfen Sie Positionen, Beschriftungen, Tab-Reihenfolge und jedes Steuerelement vor der Verwendung."),
    "Inspect skipped or unreadable parts separately; candidate generation does not resolve unknown coverage.": ("Inspectez séparément les parties ignorées ou illisibles ; la génération de candidats ne résout pas une couverture inconnue.", "Prüfen Sie übersprungene oder unlesbare Teile gesondert; die Kandidatenerzeugung klärt eine unbekannte Prüfabdeckung nicht."),
    "Document events, classes and form layouts require manual wiring": ("Les événements de document, les classes et les dispositions de formulaires nécessitent une connexion manuelle", "Dokumentereignisse, Klassen und Formularlayouts müssen manuell verbunden werden"),
    "Handler module has unresolved TODOs": ("Le module du gestionnaire contient des TODO non résolus", "Das Handlermodul enthält offene TODOs"),
    "Automatic event handlers require manual wiring": ("Les gestionnaires d’événements automatiques nécessitent une connexion manuelle", "Automatische Ereignishandler müssen manuell verbunden werden"),
    "Imported button has no readable callback": ("Le bouton importé n’a pas de procédure de rappel lisible", "Die importierte Schaltfläche hat keine lesbare Callback-Prozedur"),
    "Lifecycle and automatic events need manual migration": ("Les événements de cycle de vie et les événements automatiques nécessitent une migration manuelle", "Lebenszyklusereignisse und automatische Ereignisse benötigen eine manuelle Migration"),
    "Unclosed procedure or control block": ("Procédure ou bloc de contrôle non fermé", "Nicht abgeschlossene Prozedur oder Kontrollstruktur"),
    "Generated syntax requires review": ("La syntaxe générée doit être examinée", "Die erzeugte Syntax muss geprüft werden"),
    "VBA identifier is shadowed": ("Un identificateur VBA est masqué", "Ein VBA-Bezeichner wird überschattet"),
    "Unclosed With block requires manual migration": ("Un bloc With non fermé nécessite une migration manuelle", "Ein nicht abgeschlossener With-Block benötigt eine manuelle Migration"),
    "Optional migration review": ("Revue facultative de migration", "Optionale Migrationsprüfung"),
    "workbook and artifact paths": ("chemins des classeurs et fichiers", "Arbeitsmappen- und Dateipfade"),
    "source code and diffs": ("code source et différences", "Quellcode und Änderungen"),
    "captured values and formulas": ("valeurs et formules capturées", "erfasste Werte und Formeln"),
    "hashes": ("empreintes", "Prüfsummen"),
    "owner details and free-text notes": ("coordonnées du responsable et notes libres", "Angaben zu Verantwortlichen und Freitextnotizen"),
    "module and routine names": ("noms des modules et routines", "Modul- und Routinenamen"),
    "control and query names": ("noms des contrôles et requêtes", "Steuerelement- und Abfragenamen"),
}


def validate_language(language):
    if language not in LANGUAGES:
        raise ValueError("Invalid language")
    return language


def translate(message, language):
    if language not in ("fr", "de"):
        return message
    translations = MESSAGES.get(message)
    return translations[0 if language == "fr" else 1] if translations else message


def setup_response(setup, language):
    result = copy.deepcopy(setup)
    for check in result["checks"]:
        for key in ("label", "needed_for", "action"):
            check[key] = translate(check[key], language)
    return result


def conversion_response(report, language, inventory=None):
    """Translate presentation reasons using the scanner's existing message arrays."""
    if language == "en":
        return report
    index = LANGUAGES.index(language)
    findings = list(report.get("workbook_findings", []))
    for workbook in (inventory or {}).get("workbooks", []):
        findings.extend(workbook.get("findings", []))
        for module in workbook.get("modules", []):
            findings.extend(module.get("findings", []))
    messages = {}
    for finding in findings:
        values = finding.get("messages", [])
        if len(values) > index and isinstance(values[0], str) and isinstance(values[index], str) and values[index]:
            messages[values[0]] = values[index]

    def reason(value):
        match = re.fullmatch(r"(\d+) deterministic rewrite\(s\); source and diff retained", value)
        if match:
            return match[1] + (" réécriture(s) déterministe(s) ; source et différences conservées" if language == "fr" else " deterministische Änderung(en); Quellcode und Änderungen beibehalten")
        return messages.get(value, translate(value, language))

    records = list(report.get("checklist", {}).get("items", []))
    records.extend(report.get("buttons", {}).get("records", []))
    for key in ("modules", "power_queries", "user_interfaces"):
        for record in report.get(key, []):
            records.append(record)
            records.extend(record.get("todos", []))
            records.extend(record.get("records", []))
    for record in records:
        if "reason" in record:
            record["reason"] = reason(record["reason"])
        if "next_action" in record:
            record["next_action"] = translate(record["next_action"], language)
    return report


def handoff_response(summary, language, include_identifiers=False):
    summary["purpose"] = translate(summary["purpose"], language)
    summary["removed"] = [translate(message, language) for message in summary["removed"]]
    if not include_identifiers and language == "de":
        for index, module in enumerate(summary["modules"]):
            module["label"] = "Modul " + str(index + 1)
    return summary
