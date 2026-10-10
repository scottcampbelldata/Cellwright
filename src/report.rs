// SPDX-License-Identifier: EUPL-1.2
use crate::{
    model::{Finding, Scan, Verdict},
    scan,
};
use anyhow::{Context, Result};
use std::{
    fs::{File, OpenOptions},
    io::{BufWriter, Write},
    path::Path,
};

pub fn language_index(language: &str) -> usize {
    match language {
        "fr" => 1,
        "de" => 2,
        _ => 0,
    }
}
fn t(index: usize, texts: [&str; 3]) -> &str {
    texts[index]
}
pub fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
fn new_file(path: &Path) -> Result<File> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .with_context(|| format!("Creating {}", path.display()))
}

fn verdict_text(verdict: Verdict, index: usize) -> &'static str {
    match verdict {
        Verdict::NoKnownBlockers => t(
            index,
            [
                "No known blockers",
                "Aucun obstacle connu",
                "Keine bekannten Hindernisse",
            ],
        ),
        Verdict::NeedsEdits => t(
            index,
            [
                "Needs edits / verification",
                "Modifications / vérification",
                "Anpassung / Prüfung nötig",
            ],
        ),
        Verdict::NeedsRewrite => t(
            index,
            [
                "Needs rewrite",
                "Réécriture nécessaire",
                "Neuentwicklung nötig",
            ],
        ),
        Verdict::Unknown => t(
            index,
            [
                "Manual assessment",
                "Évaluation manuelle",
                "Manuelle Bewertung",
            ],
        ),
    }
}

fn finding_html(finding: &Finding, index: usize) -> String {
    let line = finding
        .line
        .map(|l| format!(" · {} {l}", t(index, ["line", "ligne", "Zeile"])))
        .unwrap_or_default();
    format!(
        "<li><code>{}</code>{}: {}</li>",
        escape(&finding.rule_id),
        line,
        escape(&finding.messages[index])
    )
}

pub fn html(scan: &Scan) -> String {
    let index = language_index(&scan.language);
    let title = t(
        index,
        [
            "Workbook migration inventory",
            "Inventaire de migration des classeurs",
            "Inventar zur Arbeitsmappenmigration",
        ],
    );
    let workbook_label = t(index, ["Workbooks", "Classeurs", "Arbeitsmappen"]);
    let module_label = t(
        index,
        [
            "Unique code modules",
            "Modules de code uniques",
            "Eindeutige Codemodule",
        ],
    );
    let hours_label = t(
        index,
        ["Planning hours", "Heures estimées", "Geschätzte Stunden"],
    );
    let incomplete = scan
        .workbooks
        .iter()
        .filter(|w| w.status != "inspected" || w.verdict == Verdict::Unknown)
        .count()
        + scan.discovery_errors.len();
    let mut out = format!(
        r##"<!doctype html><html lang="{}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'"><title>Cellwright · {title}</title><style>{}</style></head><body><header><a class="brand" href="#top">Cellwright<span>VBA → LibreOffice / Python</span></a><nav aria-label="{}"><a href="scan.json">JSON</a><a href="workbooks.csv">CSV</a><a href="#method">{}</a></nav></header><main id="top"><p class="eyebrow">{} / v{}</p><h1>{title}</h1><p class="intro">{}</p><dl class="metrics"><div><dt>{workbook_label}</dt><dd>{}</dd></div><div><dt>{module_label}</dt><dd>{}</dd></div><div><dt>{hours_label}</dt><dd>{:.1}-{:.1}</dd></div><div><dt>{}</dt><dd>{incomplete}</dd></div></dl><p class="notice">{}</p><section aria-labelledby="inventory-title"><h2 id="inventory-title">{workbook_label}</h2><div class="filters"><label for="search">{}<input id="search" type="search" placeholder="{}"></label><label for="verdict">{}<select id="verdict"><option value="">{}</option>"##,
        escape(&scan.language),
        STYLE,
        t(index, ["Exports", "Exports", "Exporte"]),
        t(index, ["Method", "Méthode", "Methode"]),
        t(
            index,
            [
                "Offline assessment",
                "Évaluation hors ligne",
                "Offline-Bewertung"
            ]
        ),
        scan.tool_version,
        t(
            index,
            [
                "An auditable first pass through your Excel estate. Source workbooks were read without running macros.",
                "Premier état des lieux vérifiable de vos classeurs Excel. Les fichiers ont été lus sans exécuter les macros.",
                "Eine nachvollziehbare Erstbewertung Ihrer Excel-Dateien. Arbeitsmappen wurden ohne Makroausführung gelesen."
            ]
        ),
        scan.workbooks.len(),
        scan.unique_modules,
        scan.estimated_hours_low,
        scan.estimated_hours_high,
        t(
            index,
            [
                "Manual / incomplete",
                "Manuel / incomplet",
                "Manuell / unvollständig"
            ]
        ),
        t(
            index,
            [
                "Estimates use uncalibrated planning defaults, exclude unknown work, and are not a migration quote. No known blockers does not prove LibreOffice compatibility.",
                "Les estimations utilisent des valeurs non calibrées, excluent le travail inconnu et ne constituent pas un devis. Aucun obstacle connu ne prouve pas la compatibilité LibreOffice.",
                "Schätzungen verwenden unkalibrierte Standardwerte, schließen unbekannte Arbeit aus und sind kein Angebot. Keine bekannten Hindernisse beweist keine LibreOffice-Kompatibilität."
            ]
        ),
        t(
            index,
            [
                "Find a workbook",
                "Rechercher un classeur",
                "Arbeitsmappe suchen"
            ]
        ),
        t(
            index,
            [
                "File name or path",
                "Nom ou chemin du fichier",
                "Dateiname oder Pfad"
            ]
        ),
        t(index, ["Assessment", "Évaluation", "Bewertung"]),
        t(
            index,
            [
                "All assessments",
                "Toutes les évaluations",
                "Alle Bewertungen"
            ]
        )
    );
    for verdict in [
        Verdict::NoKnownBlockers,
        Verdict::NeedsEdits,
        Verdict::NeedsRewrite,
        Verdict::Unknown,
    ] {
        out.push_str(&format!(
            "<option value=\"{}\">{}</option>",
            verdict.key(),
            verdict_text(verdict, index)
        ));
    }
    out.push_str(&format!("</select></label></div><p id=\"result-count\" class=\"muted\" aria-live=\"polite\"></p><div class=\"table-wrap\"><table id=\"inventory\"><caption class=\"sr-only\">{workbook_label}</caption><thead><tr>"));
    for (col, name) in [
        t(index, ["Workbook", "Classeur", "Arbeitsmappe"]),
        t(index, ["Assessment", "Évaluation", "Bewertung"]),
        t(index, ["Modules", "Modules", "Module"]),
        t(index, ["Findings", "Constats", "Befunde"]),
    ]
    .iter()
    .enumerate()
    {
        out.push_str(&format!("<th scope=\"col\" aria-sort=\"none\"><button type=\"button\" data-col=\"{col}\">{name} ↕</button></th>"));
    }
    out.push_str("</tr></thead><tbody>");
    for (i, workbook) in scan.workbooks.iter().enumerate() {
        let findings = workbook.findings.len()
            + workbook
                .modules
                .iter()
                .map(|m| m.findings.len())
                .sum::<usize>();
        let filename = Path::new(&workbook.path)
            .file_name()
            .unwrap_or_default()
            .to_string_lossy();
        out.push_str(&format!("<tr data-path=\"{}\" data-verdict=\"{}\"><td data-sort=\"{}\"><a href=\"#w-{i}\">{}</a><small>{}</small></td><td data-sort=\"{}\"><span class=\"badge {}\">{}</span></td><td data-sort=\"{}\">{}</td><td data-sort=\"{findings}\">{findings}</td></tr>", escape(&workbook.path.to_lowercase()), workbook.verdict.key(), escape(&workbook.path.to_lowercase()), escape(&filename), escape(&workbook.path), workbook.verdict as u8, workbook.verdict.key(), verdict_text(workbook.verdict, index), workbook.modules.len(), workbook.modules.len()));
    }
    out.push_str("</tbody></table></div></section>");
    for (i, workbook) in scan.workbooks.iter().enumerate() {
        out.push_str(&format!("<section class=\"workbook\" id=\"w-{i}\"><h2>{}</h2><p class=\"path\">{}</p><p><span class=\"badge {}\">{}</span> <code>{}</code> · {} bytes</p>", escape(&Path::new(&workbook.path).file_name().unwrap_or_default().to_string_lossy()), escape(&workbook.path), workbook.verdict.key(), verdict_text(workbook.verdict, index), escape(&workbook.status), workbook.size_bytes));
        if let Some(error) = &workbook.error {
            out.push_str(&format!("<p class=\"notice\">{}</p>", escape(error)));
        }
        out.push_str(&format!(
            "<p class=\"muted\">{}: {} · {}: {}</p>",
            t(
                index,
                ["Owner ID", "Identifiant du propriétaire", "Eigentümer-ID"]
            ),
            escape(workbook.owner.as_deref().unwrap_or("unknown")),
            t(index, ["VBA code page", "Page de code VBA", "VBA-Codepage"]),
            workbook
                .code_page
                .map(|page| page.to_string())
                .unwrap_or_else(|| "-".into())
        ));
        for form in &workbook.forms {
            out.push_str(&format!(
                "<details><summary>UserForm · {}</summary><ul>",
                escape(&form.name)
            ));
            for control in &form.controls {
                out.push_str(&format!(
                    "<li>{}: {} <code>{}</code></li>",
                    escape(&control.name),
                    escape(&control.control_type),
                    control.cached_index
                ));
            }
            if let Some(error) = &form.error {
                out.push_str(&format!("<li>{}</li>", escape(error)));
            }
            out.push_str("</ul></details>");
        }
        if !workbook.connections.is_empty() {
            out.push_str(&format!(
                "<p class=\"muted\">{}</p>",
                escape(&workbook.connections.join(" · "))
            ));
        }
        if !workbook.entry_points.is_empty() || !workbook.macro_assignments.is_empty() {
            out.push_str(&format!(
                "<p class=\"muted\">{} · {}</p>",
                escape(&workbook.entry_points.join(" · ")),
                escape(&workbook.macro_assignments.join(" · "))
            ));
        }
        if !workbook.features.is_empty() {
            out.push_str(&format!(
                "<p class=\"muted\">{}</p>",
                escape(&workbook.features.join(" · "))
            ));
        }
        if !workbook.references.is_empty() {
            out.push_str(&format!(
                "<details><summary>{}</summary><ul>",
                t(
                    index,
                    [
                        "Library references",
                        "Références de bibliothèques",
                        "Bibliotheksreferenzen"
                    ]
                )
            ));
            for reference in &workbook.references {
                out.push_str(&format!("<li>{}</li>", escape(reference)));
            }
            out.push_str("</ul></details>");
        }
        out.push_str("<ul class=\"findings\">");
        for finding in &workbook.findings {
            out.push_str(&finding_html(finding, index));
        }
        out.push_str("</ul>");
        for module in &workbook.modules {
            out.push_str(&format!("<details><summary><strong>{}</strong> <span class=\"muted\">{} · {} {} · {}</span></summary><p><code>{}</code></p><ul class=\"findings\">", escape(&module.name), escape(&module.kind), module.code_lines, t(index,["code lines", "lignes de code", "Codezeilen"]), verdict_text(module.verdict, index), module.normalized_sha256));
            for finding in &module.findings {
                out.push_str(&finding_html(finding, index));
            }
            out.push_str("</ul>");
            if !module.api_usage.is_empty() {
                out.push_str(&format!("<p class=\"muted\">{}</p><ul>",t(index,["LibreOffice IDL declarations; execution parity is established only by a supplied test case.","Déclarations IDL LibreOffice ; seul un cas de test fourni établit la parité d’exécution.","LibreOffice-IDL-Deklarationen; Ausführungsgleichheit wird nur durch einen vorgegebenen Testfall belegt."])));
                for call in &module.api_usage {
                    out.push_str(&format!(
                        "<li><code>{}.{}</code> · {} · {}</li>",
                        escape(&call.object_type),
                        escape(&call.member),
                        call.line,
                        if call.declared {
                            t(index, ["declared", "déclaré", "deklariert"])
                        } else {
                            t(index, ["not declared", "non déclaré", "nicht deklariert"])
                        }
                    ));
                }
                out.push_str("</ul>");
            }
            if let Some(source) = &module.source {
                out.push_str(&format!("<pre><code>{}</code></pre>", escape(source)));
            }
            out.push_str("</details>");
        }
        for query in &workbook.queries {
            out.push_str(&format!(
                "<details><summary>Power Query · {}</summary><p><code>{}</code></p>",
                escape(&query.name),
                query.sha256
            ));
            if let Some(source) = &query.source {
                out.push_str(&format!("<pre><code>{}</code></pre>", escape(source)));
            }
            out.push_str(&format!(
                "<p class=\"muted\">{} · {} · {}</p>",
                escape(&query.names.join(" · ")),
                escape(&query.steps.join(" → ")),
                escape(&query.sources.join(" · "))
            ));
            out.push_str("</details>");
        }
        out.push_str("</section>");
    }
    out.push_str(&format!(
        "<section><h2>{}</h2>",
        t(
            index,
            ["Duplicate modules", "Modules dupliqués", "Doppelte Module"]
        )
    ));
    if scan.duplicates.is_empty() {
        out.push_str(&format!(
            "<p class=\"muted\">{}</p>",
            t(
                index,
                [
                    "No duplicate code modules found.",
                    "Aucun module de code dupliqué trouvé.",
                    "Keine doppelten Codemodule gefunden."
                ]
            )
        ));
    }
    for group in &scan.duplicates {
        out.push_str(&format!(
            "<details><summary>{} {} · <code>{}</code></summary><ul>",
            group.members.len(),
            t(index, ["copies", "copies", "Kopien"]),
            &group.hash[..12]
        ));
        for member in &group.members {
            out.push_str(&format!(
                "<li>{} · {}</li>",
                escape(&member.workbook),
                escape(&member.module)
            ));
        }
        out.push_str("</ul></details>");
    }
    out.push_str("</section>");
    if !scan.discovery_errors.is_empty() {
        out.push_str(&format!(
            "<section><h2>{}</h2><ul>",
            t(
                index,
                [
                    "Discovery errors",
                    "Erreurs de recherche",
                    "Fehler bei der Dateisuche"
                ]
            )
        ));
        for error in &scan.discovery_errors {
            out.push_str(&format!("<li>{}</li>", escape(error)));
        }
        out.push_str("</ul></section>");
    }
    out.push_str(&format!("<section id=\"method\"><h2>{}</h2><p>{}</p><pre><code>module_hours = {:.2} + code_lines × {:.3} + Σ(rule.hours × min(occurrences, {})) + {:.2}\nform_hours_per_file = Σ({:.2} + min(control_sites, {}) × {:.2})\nhours = unique_module_hours + workbook_finding_hours + form_hours_per_file\nrange = hours × {:.2} … hours × {:.2}</code></pre><p>{}</p><p>{}: <strong>{}</strong>. {}</p><p>{}</p></section></main><footer>Cellwright · {} · schema {}</footer><script>{}</script></body></html>", t(index,["Assessment method", "Méthode d’évaluation", "Bewertungsmethode"]), t(index,["Nonempty code modules are counted once per normalized token hash and module type. Empty modules cost zero; document modules containing only attributes, options or empty procedures omit base and testing hours. String literals retain their case. Feature and form costs are added per file, with control sites capped per form. Deduplication does not remove integration or deployment work.", "Les modules non vides sont comptés une fois par empreinte normalisée et type. Les modules vides coûtent zéro ; les modules document contenant uniquement des attributs, options ou procédures vides n’ajoutent pas les heures de base et de test. La casse des chaînes est conservée. Les fonctionnalités et formulaires sont pondérés par fichier, avec un plafond de contrôles par formulaire. L’intégration et le déploiement restent à évaluer.", "Nicht leere Codemodule werden pro normalisiertem Token-Hash und Modultyp einmal gezählt. Leere Module kosten null; Dokumentmodule nur mit Attributen, Optionen oder leeren Prozeduren erhalten keine Basis- und Teststunden. Zeichenfolgen behalten ihre Großschreibung. Funktions- und Formularkosten werden pro Datei addiert, mit einer Obergrenze für Steuerelemente pro Formular. Integration und Bereitstellung bleiben separat zu bewerten."]), scan.estimate.base_hours, scan.estimate.hours_per_code_line, scan.estimate.occurrence_cap, scan.estimate.test_hours, scan.estimate.hours_per_userform, scan.estimate.control_site_cap, scan.estimate.hours_per_control_site, scan.estimate.low_multiplier, scan.estimate.high_multiplier,
        t(index,["The full rule set and the exact weights used are recorded in scan.json. Token rules and partial type inference cannot resolve every shadowed name, alias or dynamic call.", "Les règles et pondérations utilisées sont enregistrées dans scan.json. Les règles lexicales et l’inférence partielle ne résolvent pas tous les noms masqués, alias ou appels dynamiques.", "Regeln und verwendete Gewichtungen stehen in scan.json. Tokenregeln und teilweise Typinferenz erkennen nicht alle verdeckten Namen, Aliase oder dynamischen Aufrufe."]), t(index,["Source included", "Source incluse", "Quelltext enthalten"]), if scan.source_included { t(index,["yes", "oui", "ja"]) } else { t(index,["no", "non", "nein"]) }, t(index,["Paths, module names, hashes and references remain in no-source reports.", "Les chemins, noms, empreintes et références restent dans les rapports sans source.", "Pfade, Namen, Hashes und Referenzen bleiben in Berichten ohne Quelltext enthalten."]), t(index,["XLS/XLSB feature coverage is partial. Source/cache flags are heuristics; UserForm layouts need manual migration. Declared API members are not execution proof.", "La couverture XLS/XLSB est partielle. Les écarts source/cache sont heuristiques ; les formulaires nécessitent une migration manuelle. Les membres déclarés ne prouvent pas le comportement.", "XLS/XLSB-Funktionen werden teilweise erfasst. Quelltext/Cache-Hinweise sind heuristisch; Formulare erfordern manuelle Migration. Deklarierte API-Mitglieder sind kein Ausführungsnachweis."]), scan.tool_version, scan.schema_version, SCRIPT));
    out
}

// Prefix potentially executable spreadsheet cells, including whitespace-obscured formulas.
pub fn csv_cell(value: &str) -> String {
    if value.starts_with(['\t', '\r', '\n']) || value.trim_start().starts_with(['=', '+', '-', '@'])
    {
        format!("'{value}")
    } else {
        value.into()
    }
}

fn csv_writer(path: &Path) -> Result<csv::Writer<File>> {
    let mut file = new_file(path)?;
    file.write_all(b"\xef\xbb\xbf")?;
    Ok(csv::Writer::from_writer(file))
}

pub fn write(scan: &Scan, out: &Path) -> Result<()> {
    let mut json = BufWriter::new(new_file(&out.join("scan.json"))?);
    serde_json::to_writer_pretty(&mut json, scan)?;
    json.flush()?;
    new_file(&out.join("report.html"))?.write_all(html(scan).as_bytes())?;
    let index = language_index(&scan.language);
    let mut workbooks = csv_writer(&out.join("workbooks.csv"))?;
    workbooks.write_record([
        "path",
        "size_bytes",
        "modified_unix_seconds",
        "status",
        "verdict",
        "module_count",
        "query_sections",
        "finding_count",
        "protected",
        "features",
        "error",
        "owner_id",
        "code_page",
        "entry_points",
        "connections",
    ])?;
    let mut modules = csv_writer(&out.join("modules.csv"))?;
    modules.write_record([
        "path",
        "module",
        "type",
        "lines",
        "code_lines",
        "normalized_sha256",
        "verdict",
        "estimated_hours",
    ])?;
    let mut findings = csv_writer(&out.join("findings.csv"))?;
    findings.write_record([
        "path",
        "module",
        "line",
        "rule_id",
        "category",
        "verdict",
        "message",
        "default_hours",
    ])?;
    for workbook in &scan.workbooks {
        workbooks.write_record(
            [
                workbook.path.clone(),
                workbook.size_bytes.to_string(),
                workbook
                    .modified_unix_seconds
                    .map(|t| t.to_string())
                    .unwrap_or_default(),
                workbook.status.clone(),
                workbook.verdict.key().into(),
                workbook.modules.len().to_string(),
                workbook.queries.len().to_string(),
                (workbook.findings.len()
                    + workbook
                        .modules
                        .iter()
                        .map(|m| m.findings.len())
                        .sum::<usize>())
                .to_string(),
                workbook
                    .protected
                    .map(|p| p.to_string())
                    .unwrap_or_else(|| "unknown".into()),
                workbook.features.join("; "),
                workbook.error.clone().unwrap_or_default(),
                workbook.owner.clone().unwrap_or_default(),
                workbook
                    .code_page
                    .map(|page| page.to_string())
                    .unwrap_or_default(),
                workbook.entry_points.join("; "),
                workbook.connections.join("; "),
            ]
            .iter()
            .map(|s| csv_cell(s)),
        )?;
        for module in &workbook.modules {
            modules.write_record(
                [
                    workbook.path.clone(),
                    module.name.clone(),
                    module.kind.clone(),
                    module.lines.to_string(),
                    module.code_lines.to_string(),
                    module.normalized_sha256.clone(),
                    module.verdict.key().into(),
                    format!("{:.2}", module.estimated_hours),
                ]
                .iter()
                .map(|s| csv_cell(s)),
            )?;
        }
        for (module, finding) in workbook.findings.iter().map(|f| ("", f)).chain(
            workbook
                .modules
                .iter()
                .flat_map(|m| m.findings.iter().map(move |f| (m.name.as_str(), f))),
        ) {
            findings.write_record(
                [
                    workbook.path.clone(),
                    module.into(),
                    finding.line.map(|l| l.to_string()).unwrap_or_default(),
                    finding.rule_id.clone(),
                    finding.category.clone(),
                    finding.verdict.key().into(),
                    finding.messages[index].clone(),
                    finding.hours.to_string(),
                ]
                .iter()
                .map(|s| csv_cell(s)),
            )?;
        }
    }
    workbooks.flush()?;
    modules.flush()?;
    findings.flush()?;
    Ok(())
}

fn safe_name(name: &str) -> String {
    name.chars()
        .take(64)
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

pub fn extract(scan: &Scan, out: &Path) -> Result<()> {
    scan::prepare_output(out)?;
    let mut manifest = Vec::new();
    for (i, workbook) in scan.workbooks.iter().enumerate() {
        let folder = out.join(format!(
            "{i:05}_{}",
            safe_name(
                &Path::new(&workbook.path)
                    .file_stem()
                    .unwrap_or_default()
                    .to_string_lossy()
            )
        ));
        if workbook.modules.is_empty() && workbook.queries.is_empty() && workbook.forms.is_empty() {
            continue;
        }
        std::fs::create_dir(&folder)?;
        for (j, module) in workbook.modules.iter().enumerate() {
            let extension = match module.kind.as_str() {
                "class" | "document" => "cls",
                "form" => "frm",
                _ => "bas",
            };
            let name = format!("{j:04}_{}.{extension}", safe_name(&module.name));
            if let Some(source) = &module.source {
                new_file(&folder.join(&name))?.write_all(source.as_bytes())?;
                manifest.push(serde_json::json!({"workbook": workbook.path, "module": module.name, "file": folder.file_name().unwrap().to_string_lossy().to_string() + "/" + &name, "normalized_sha256": module.normalized_sha256}));
            }
        }
        for (j, query) in workbook.queries.iter().enumerate() {
            let name = format!(
                "query_{j:04}_{}.m",
                safe_name(
                    Path::new(&query.name)
                        .file_stem()
                        .unwrap_or_default()
                        .to_str()
                        .unwrap_or("section")
                )
            );
            if let Some(source) = &query.source {
                new_file(&folder.join(&name))?.write_all(source.as_bytes())?;
                manifest.push(serde_json::json!({"workbook": workbook.path, "query_section": query.name, "file": folder.file_name().unwrap().to_string_lossy().to_string() + "/" + &name, "sha256": query.sha256}));
            }
        }
        for (j, form) in workbook.forms.iter().enumerate() {
            if let Some(layout) = &form.layout {
                use base64::Engine;
                let name = format!("form_{j:04}_{}.designer.cfb", safe_name(&form.name));
                let bytes = base64::engine::general_purpose::STANDARD.decode(layout)?;
                new_file(&folder.join(&name))?.write_all(&bytes)?;
                manifest.push(serde_json::json!({"workbook":workbook.path,"form":form.name,"file":folder.file_name().unwrap().to_string_lossy().to_string()+"/"+&name}));
            }
        }
    }
    serde_json::to_writer_pretty(new_file(&out.join("manifest.json"))?, &manifest)?;
    Ok(())
}

const STYLE: &str = r#"
:root{color-scheme:light;--ink:#20232b;--muted:#5b6372;--line:#dce0e9;--accent:#305aca}*{box-sizing:border-box}body{margin:0;background:#fafbfe;color:var(--ink);font:16px/1.6 system-ui,-apple-system,sans-serif}header{display:flex;justify-content:space-between;align-items:center;padding:22px 5%;border-bottom:1px solid var(--line);background:#fff}.brand{color:var(--ink);font-size:24px;font-weight:750;text-decoration:none;letter-spacing:-.8px}.brand span{display:block;font-size:11px;letter-spacing:1px;font-weight:500;color:var(--muted)}nav{display:flex;gap:24px}a{color:var(--accent);text-underline-offset:3px}main{max-width:1160px;margin:48px auto;padding:0 28px}h1{font-size:clamp(30px,4vw,46px);line-height:1.2;letter-spacing:-1.5px;margin:12px 0 18px}h2{font-size:23px;letter-spacing:-.4px;overflow-wrap:anywhere}p{max-width:90ch}.eyebrow{text-transform:uppercase;letter-spacing:2px;font-size:12px;color:var(--accent);font-weight:700}.intro{color:var(--muted);max-width:70ch}.metrics{display:grid;grid-template-columns:repeat(4,1fr);padding:24px 0;margin:28px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);gap:24px}dt{font-size:12px;color:var(--muted)}dd{margin:6px 0 0;font-size:32px;line-height:1.2;letter-spacing:-1px;font-variant-numeric:tabular-nums}.notice{background:#fff5dd;border-left:3px solid #b27a13;padding:14px 18px;font-size:14px}.filters{display:flex;gap:20px;flex-wrap:wrap;margin:20px 0}.filters label{font-size:13px;font-weight:600}.filters input,.filters select{display:block;margin-top:6px;padding:10px 12px;font:inherit;border:1px solid #b6bccb;border-radius:4px;background:#fff;min-width:240px}section{margin:42px 0}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;background:#fff;font-size:14px}th,td{padding:15px 18px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#f0f2f8}th button{font:inherit;font-weight:650;border:0;background:none;color:inherit;cursor:pointer;padding:0;text-align:left}td small{display:block;margin-top:5px;color:var(--muted);font-size:11px;overflow-wrap:anywhere;max-width:520px}.badge{display:inline-block;border:1px solid #b6c5e6;background:#eef2fc;border-radius:3px;padding:3px 8px;white-space:nowrap;font-size:11px;font-weight:650}.needs_edits{background:#fff4dd;border-color:#dfc685}.needs_rewrite{background:#ffebe5;border-color:#e1aea0}.unknown{background:#edf0f7;border-color:#b9c2d3}.workbook{padding-top:20px;border-top:1px solid var(--line);scroll-margin-top:20px}.path,.muted{color:var(--muted);font-size:13px;overflow-wrap:anywhere}details{margin:12px 0;border-bottom:1px solid var(--line);padding:10px 0}summary{cursor:pointer;overflow-wrap:anywhere}summary .muted{margin-left:8px}pre{overflow:auto;background:#20232b;color:#e5e9f4;padding:20px;border-radius:4px;font-size:12px;line-height:1.7;max-height:600px}code{font-family:ui-monospace,Consolas,monospace;font-size:.88em;overflow-wrap:anywhere}.findings{padding-left:24px;font-size:14px}.findings li{margin:10px 0}footer{border-top:1px solid var(--line);padding:24px 5%;color:var(--muted);font-size:12px}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #305aca;outline-offset:3px}[hidden]{display:none!important}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}@media(max-width:720px){main{margin-top:30px;padding:0 18px}header{padding:16px 18px;gap:14px;flex-wrap:wrap}nav{gap:16px}.metrics{grid-template-columns:repeat(2,1fr)}th,td{padding:12px}.filters input,.filters select{width:100%}.filters label{width:100%}}
"#;

const SCRIPT: &str = r#"
const table=document.getElementById('inventory'),rows=Array.from(table.tBodies[0].rows),search=document.getElementById('search'),verdict=document.getElementById('verdict');
function filter(){const q=search.value.toLowerCase();let n=0;for(const row of rows){row.hidden=!row.dataset.path.includes(q)||(verdict.value&&row.dataset.verdict!==verdict.value);if(!row.hidden)n++;}document.getElementById('result-count').textContent=n+' / '+rows.length;}
search.addEventListener('input',filter);verdict.addEventListener('change',filter);filter();
for(const button of table.querySelectorAll('th button'))button.addEventListener('click',()=>{const th=button.closest('th'),ascending=th.getAttribute('aria-sort')!=='ascending',col=Number(button.dataset.col);for(const h of table.querySelectorAll('th'))h.setAttribute('aria-sort','none');th.setAttribute('aria-sort',ascending?'ascending':'descending');rows.sort((a,b)=>{const av=a.cells[col].dataset.sort,bv=b.cells[col].dataset.sort;const cmp=col===0?av.localeCompare(bv):Number(av)-Number(bv);return ascending?cmp:-cmp;});for(const row of rows)table.tBodies[0].appendChild(row);});
"#;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn escapes_html_and_blocks_csv_formulas() {
        assert_eq!(escape("<script>\"&'"), "&lt;script&gt;&quot;&amp;&#39;");
        assert_eq!(
            csv_cell("  =HYPERLINK(\"evil\")"),
            "'  =HYPERLINK(\"evil\")"
        );
        assert_eq!(csv_cell("Module1"), "Module1");
        assert_eq!(safe_name("../../CON:<script>"), "______CON__script_");
    }
}
