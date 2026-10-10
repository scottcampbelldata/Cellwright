// SPDX-License-Identifier: EUPL-1.2
use crate::{
    model::{Query, Workbook},
    ovba,
    rules::{self, Rule, Weights},
};
use anyhow::{Context, Result, bail, ensure};
use base64::{Engine, engine::general_purpose::STANDARD};
use quick_xml::{NsReader, XmlVersion, events::Event, name::ResolveResult};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::{Cursor, Read, Seek, Write},
    path::Path,
    time::UNIX_EPOCH,
};
use zip::ZipArchive;

pub const MAX_FILE: u64 = 128 * 1024 * 1024;
pub const MAX_PART: u64 = 16 * 1024 * 1024;
pub const MAX_TOTAL: u64 = 256 * 1024 * 1024;
pub const MAX_ENTRIES: usize = 10_000;

fn bounded_read(reader: impl Read, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader.take(limit + 1).read_to_end(&mut bytes)?;
    ensure!(
        bytes.len() as u64 <= limit,
        "Decompressed part exceeds {} MiB limit",
        limit / 1024 / 1024
    );
    Ok(bytes)
}

fn check_zip<R: Read + Seek>(zip: &mut ZipArchive<R>, skip_non_vba: bool) -> Result<Vec<String>> {
    ensure!(zip.len() <= MAX_ENTRIES, "ZIP has too many entries");
    let mut total = 0_u64;
    let mut names = BTreeSet::new();
    let mut skipped = Vec::new();
    for i in 0..zip.len() {
        let entry = zip.by_index_raw(i)?;
        ensure!(names.insert(entry.name().to_owned()), "Duplicate ZIP entry");
        ensure!(
            !entry.encrypted(),
            "Encrypted ZIP entry cannot be inspected"
        );
        if skip_non_vba
            && entry.size() > MAX_PART
            && !entry
                .name()
                .to_ascii_lowercase()
                .ends_with("vbaproject.bin")
        {
            skipped.push(format!(
                "Skipped ZIP part {}: {} expanded bytes exceed the {} MiB per-part limit",
                entry.name(),
                entry.size(),
                MAX_PART / 1024 / 1024
            ));
            continue;
        }
        ensure!(
            entry.size() <= MAX_PART,
            "ZIP part {} expands to {} bytes, exceeding the {} MiB per-part scan limit; archive too large to inspect",
            entry.name(),
            entry.size(),
            MAX_PART / 1024 / 1024
        );
        total = total
            .checked_add(entry.size())
            .context("ZIP size overflow")?;
        ensure!(
            total <= MAX_TOTAL,
            "ZIP declared expansion reaches {} bytes, exceeding the {} MiB aggregate scan limit; archive too large to inspect",
            total,
            MAX_TOTAL / 1024 / 1024
        );
    }
    Ok(skipped)
}

fn xml_text(bytes: &[u8]) -> Result<String> {
    let (encoding, skip) = if bytes.starts_with(&[0xff, 0xfe]) {
        (Some(encoding_rs::UTF_16LE), 2)
    } else if bytes.starts_with(&[0xfe, 0xff]) {
        (Some(encoding_rs::UTF_16BE), 2)
    } else if bytes.starts_with(b"<\0") {
        (Some(encoding_rs::UTF_16LE), 0)
    } else if bytes.starts_with(b"\0<") {
        (Some(encoding_rs::UTF_16BE), 0)
    } else {
        (None, 0)
    };
    if let Some(encoding) = encoding {
        let (text, errors) = encoding.decode_without_bom_handling(&bytes[skip..]);
        ensure!(!errors, "Invalid UTF-16 XML");
        Ok(text.into_owned())
    } else {
        Ok(std::str::from_utf8(bytes)?
            .trim_start_matches('\u{feff}')
            .into())
    }
}

pub fn inspect_xml(bytes: &[u8], workbook: &mut Workbook) -> Result<Vec<String>> {
    let text = xml_text(bytes)?;
    let mut reader = NsReader::from_str(&text);
    let (mut mashup, mut depth, mut events) = (None::<String>, 0_usize, 0_usize);
    let mut mashups = Vec::new();
    loop {
        let (namespace, event) = reader.read_resolved_event()?;
        let is_mashup_namespace = matches!(namespace, ResolveResult::Bound(ns) if ns.as_ref() == b"http://schemas.microsoft.com/DataMashup");
        match &event {
            Event::Start(_) => {
                depth += 1;
                ensure!(depth <= 128, "XML nesting limit exceeded");
            }
            Event::End(_) => {
                depth = depth.checked_sub(1).context("Unbalanced XML")?;
            }
            Event::Eof => ensure!(depth == 0, "Truncated XML"),
            _ => (),
        }
        match event {
            Event::Start(e) | Event::Empty(e) => {
                let name = String::from_utf8_lossy(e.local_name().as_ref()).into_owned();
                if name == "DataMashup" && is_mashup_namespace {
                    mashup = Some(String::new());
                }
                if name == "connection" {
                    add_feature(workbook, "external_connections");
                    let mut summary = Vec::new();
                    for attribute in e.attributes() {
                        let attribute = attribute?;
                        if [b"id".as_slice(), b"name", b"type"].contains(&attribute.key.as_ref()) {
                            summary.push(format!(
                                "{}={}",
                                String::from_utf8_lossy(attribute.key.as_ref()),
                                attribute.decoded_and_normalized_value(
                                    XmlVersion::Implicit1_0,
                                    reader.decoder()
                                )?
                            ));
                        }
                    }
                    if !summary.is_empty() {
                        workbook.connections.push(summary.join(" · "));
                    }
                }
                if name == "control" {
                    add_feature(workbook, "form_controls");
                }
                if name == "oleObject" {
                    add_feature(workbook, "embedded_ole");
                }
                for attribute in e.attributes() {
                    let attribute = attribute?;
                    let key =
                        String::from_utf8_lossy(attribute.key.local_name().as_ref()).into_owned();
                    let value = attribute
                        .decoded_and_normalized_value(XmlVersion::Implicit1_0, reader.decoder())?;
                    if ["macro", "onAction"].contains(&key.as_str()) && !value.is_empty() {
                        add_feature(workbook, "macro_assignment");
                        if !workbook.macro_assignments.contains(&value.to_string()) {
                            workbook.macro_assignments.push(value.to_string());
                        }
                    }
                }
            }
            Event::Text(e) if mashup.is_some() => {
                mashup
                    .as_mut()
                    .unwrap()
                    .push_str(&quick_xml::escape::unescape(&String::from_utf8_lossy(
                        e.as_ref(),
                    ))?)
            }
            Event::CData(e) if mashup.is_some() => mashup
                .as_mut()
                .unwrap()
                .push_str(std::str::from_utf8(e.as_ref())?),
            Event::GeneralRef(e) if mashup.is_some() => {
                mashup
                    .as_mut()
                    .unwrap()
                    .push_str(&quick_xml::escape::unescape(&format!(
                        "&{};",
                        std::str::from_utf8(e.as_ref())?
                    ))?)
            }
            Event::End(e) if e.local_name().as_ref() == b"DataMashup" => {
                if let Some(m) = mashup.take() {
                    mashups.push(m);
                }
            }
            Event::DocType(_) => bail!("XML DTDs are not allowed"),
            Event::Eof => break,
            _ => (),
        }
        events += 1;
        ensure!(events <= 1_000_000, "XML event count limit exceeded");
    }
    Ok(mashups)
}

pub fn extract_mashup(encoded: &str) -> Result<Vec<Query>> {
    let compact: String = encoded.chars().filter(|c| !c.is_whitespace()).collect();
    ensure!(compact.len() as u64 <= MAX_PART, "DataMashup too large");
    let bytes = STANDARD.decode(compact)?;
    ensure!(bytes.len() >= 8, "Truncated DataMashup header");
    let version = u32::from_le_bytes(bytes[..4].try_into()?);
    ensure!(version == 0, "Unsupported DataMashup version {version}");
    let len = u32::from_le_bytes(bytes[4..8].try_into()?) as usize;
    let package = bytes
        .get(
            8..8_usize
                .checked_add(len)
                .context("DataMashup length overflow")?,
        )
        .context("Truncated DataMashup package")?;
    let mut zip = ZipArchive::new(Cursor::new(package))?;
    check_zip(&mut zip, false)?;
    let mut queries = Vec::new();
    for i in 0..zip.len() {
        let entry = zip.by_index(i)?;
        let name = entry.name().trim_start_matches('/').to_owned();
        if name.starts_with("Formulas/") && name.ends_with(".m") {
            let source = String::from_utf8(bounded_read(entry, MAX_PART)?)?
                .trim_start_matches('\u{feff}')
                .to_owned();
            let information = crate::m_info::inspect(&source);
            queries.push(Query {
                name,
                sha256: Sha256::digest(source.as_bytes())
                    .iter()
                    .map(|b| format!("{b:02x}"))
                    .collect(),
                source: Some(source),
                names: information.names,
                steps: information.steps,
                sources: information.sources,
            });
        }
    }
    ensure!(!queries.is_empty(), "DataMashup has no M formula section");
    Ok(queries)
}

fn add_feature(workbook: &mut Workbook, feature: &str) {
    if !workbook.features.iter().any(|f| f == feature) {
        workbook.features.push(feature.into());
    }
}

// MS-OVBA 2.4.3.3: decode only the CMG protection bits, never the password record.
fn project_protection(hex: &str) -> Result<bool> {
    ensure!(
        hex.is_ascii() && (22..=28).contains(&hex.len()) && hex.len().is_multiple_of(2),
        "Invalid CMG protection record"
    );
    let bytes: Vec<u8> = (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16))
        .collect::<std::result::Result<_, _>>()?;
    let seed = bytes[0];
    ensure!(seed ^ bytes[1] == 2, "Unsupported CMG version");
    let ignored = ((seed & 6) / 2) as usize;
    ensure!(bytes.len() == 3 + ignored + 8, "Invalid CMG length");
    let (mut plain1, mut enc1, mut enc2) = (seed ^ bytes[2], bytes[2], bytes[1]);
    let mut plain = Vec::new();
    for enc in &bytes[3..] {
        let byte = enc ^ enc2.wrapping_add(plain1);
        plain.push(byte);
        (plain1, enc2, enc1) = (byte, enc1, *enc);
    }
    ensure!(
        u32::from_le_bytes(plain[ignored..ignored + 4].try_into()?) == 4,
        "Invalid CMG state size"
    );
    let state = u32::from_le_bytes(plain[ignored + 4..].try_into()?);
    Ok(state & 7 != 0)
}

fn read_vba(
    bytes: &[u8],
    workbook: &mut Workbook,
    rules: &[Rule],
    weights: &Weights,
    skip_protected: bool,
) -> Result<()> {
    let mut cfb = cfb::CompoundFile::open(Cursor::new(bytes))?;
    let entries: Vec<_> = cfb
        .walk()
        .take(MAX_ENTRIES + 1)
        .map(|e| {
            (
                e.path().to_owned(),
                e.name().to_owned(),
                e.len(),
                e.is_stream(),
            )
        })
        .collect();
    ensure!(entries.len() <= MAX_ENTRIES, "CFB has too many entries");
    ensure!(
        entries
            .iter()
            .all(|e| e.2 <= MAX_PART && e.0.components().count() <= 32),
        "CFB stream size or depth limit exceeded"
    );
    if entries
        .iter()
        .any(|e| e.1 == "EncryptedPackage" || e.1 == "EncryptionInfo")
    {
        workbook.status = "encrypted".into();
        workbook.error = Some("Password-to-open encryption; inspection skipped".into());
        return Ok(());
    }
    if entries
        .iter()
        .any(|e| e.1.eq_ignore_ascii_case("Workbook") || e.1.eq_ignore_ascii_case("Book"))
    {
        add_feature(workbook, "legacy_features_uninspected");
    }
    let has_vba = entries.iter().any(|e| {
        e.1.eq_ignore_ascii_case("dir")
            && e.0.to_string_lossy().to_ascii_lowercase().contains("vba")
    });
    if !has_vba {
        return Ok(());
    }
    let mut kinds = BTreeMap::new();
    let dir_entry = entries
        .iter()
        .find(|e| {
            e.1.eq_ignore_ascii_case("dir")
                && e.0
                    .parent()
                    .is_some_and(|p| p.file_name().is_some_and(|n| n.eq_ignore_ascii_case("VBA")))
        })
        .context("Missing VBA dir stream")?;
    let dir = bounded_read(cfb.open_stream(&dir_entry.0)?, MAX_PART)?;
    let project = ovba::parse_dir(&ovba::decompress(&dir, MAX_PART as usize)?)?;
    workbook.code_page = Some(project.code_page);
    if let Some(project) = entries.iter().find(|e| e.1.eq_ignore_ascii_case("PROJECT")) {
        let data = bounded_read(cfb.open_stream(&project.0)?, MAX_PART)?;
        let text = ovba::decode(&data, workbook.code_page.unwrap())?;
        if let Some(cmg) = text
            .lines()
            .find_map(|l| l.strip_prefix("CMG=\"").and_then(|s| s.strip_suffix('"')))
        {
            workbook.protected = Some(project_protection(cmg)?);
        }
        for line in text.lines() {
            if let Some((key, value)) = line.split_once('=') {
                let kind = match key {
                    "Module" => "standard",
                    "Class" => "class",
                    "Document" => "document",
                    "BaseClass" => "form",
                    _ => continue,
                };
                kinds.insert(value.split('/').next().unwrap_or(value).to_owned(), kind);
                if kind == "form" {
                    add_feature(workbook, "userforms");
                }
            }
        }
    }
    if skip_protected && workbook.protected != Some(false) {
        workbook.status = "skipped_protected".into();
        workbook.error = Some("VBA project protection is present or cannot be determined".into());
        return Ok(());
    }
    let mut form_bytes = 0;
    for (name, _) in kinds.iter().filter(|(_, kind)| **kind == "form") {
        let storage = dir_entry
            .0
            .parent()
            .and_then(|parent| parent.parent())
            .context("Missing project root")?
            .join(name);
        let mut layout =
            cfb::CompoundFile::create_with_version(cfb::Version::V3, Cursor::new(Vec::new()))?;
        let mut controls = Vec::new();
        let mut error = Some("Missing form designer f stream".to_string());
        for entry in entries.iter().filter(|entry| entry.0.starts_with(&storage)) {
            let relative = entry.0.strip_prefix(&storage)?;
            if relative.as_os_str().is_empty() {
                continue;
            }
            let target = Path::new("/").join(relative);
            if entry.3 {
                let data = bounded_read(cfb.open_stream(&entry.0)?, MAX_PART)?;
                form_bytes += data.len();
                ensure!(
                    form_bytes as u64 <= MAX_PART,
                    "Form designer total exceeds limit"
                );
                if relative == Path::new("f") {
                    match crate::forms::controls(&data, project.code_page) {
                        Ok(values) => {
                            controls = values;
                            error = None;
                        }
                        Err(e) => error = Some(format!("{e:#}")),
                    }
                }
                layout.create_stream(target)?.write_all(&data)?;
            } else {
                layout.create_storage(target)?;
            }
        }
        if error.is_some()
            || controls
                .iter()
                .any(|control| control.control_type == "CustomOrUnknown")
        {
            add_feature(workbook, "forms_layout_uninspected");
        }
        workbook.forms.push(crate::model::UserForm {
            name: name.clone(),
            controls,
            error,
            layout: Some(STANDARD.encode(layout.into_inner().into_inner())),
        });
    }
    for name in project.references {
        let lower = name.to_lowercase();
        if !["vba", "excel", "stdole", "office"].contains(
            &name
                .split(':')
                .next()
                .unwrap_or("")
                .to_ascii_lowercase()
                .as_str(),
        ) && !rules.iter().any(|r| {
            r.kind == "reference" && r.pattern.iter().any(|p| lower.contains(&p.to_lowercase()))
        }) {
            add_feature(workbook, "nonstandard_reference");
        }
        workbook.references.push(name);
    }
    let mut source_size = 0;
    for module in project.modules {
        let name = &module.name;
        let path = dir_entry
            .0
            .parent()
            .context("Missing VBA storage")?
            .join(&module.stream);
        let data = bounded_read(cfb.open_stream(path)?, MAX_PART)?;
        let compressed = data
            .get(module.offset..)
            .with_context(|| format!("Source offset past module {name}"))?;
        let source = if compressed.is_empty() {
            String::new()
        } else {
            ovba::decode(
                &ovba::decompress(compressed, MAX_PART as usize)?,
                project.code_page,
            )?
        };
        source_size += source.len();
        ensure!(
            source_size as u64 <= MAX_TOTAL,
            "VBA source size limit exceeded"
        );
        let analyzed = rules::analyze(
            name,
            kinds.get(name).copied().unwrap_or(if module.procedural {
                "standard"
            } else {
                "unknown"
            }),
            source.clone(),
            rules,
            weights,
        );
        if module.procedural && analyzed.code_lines == 0 && module.offset > 256 {
            add_feature(workbook, "source_cache_discrepancy");
        }
        let tokens = crate::lexer::lex(&source);
        for pair in tokens.windows(2) {
            if pair[0].text == "sub"
                && (pair[1].text.starts_with("workbook_")
                    || pair[1].text.starts_with("worksheet_")
                    || ["auto_open", "auto_close"].contains(&pair[1].text.as_str()))
            {
                workbook
                    .entry_points
                    .push(format!("{name}.{}:{}", pair[1].text, pair[1].line));
            }
        }
        workbook.modules.push(analyzed);
    }
    Ok(())
}

pub fn inspect(
    path: &Path,
    rules: &[Rule],
    weights: &Weights,
    skip_protected: bool,
) -> Result<Workbook> {
    let file = File::open(path)?;
    let metadata = file.metadata()?;
    ensure!(metadata.is_file(), "Input is not a regular file");
    ensure!(metadata.len() <= MAX_FILE, "Workbook exceeds 128 MiB limit");
    let bytes = bounded_read(file, MAX_FILE)?;
    let mut workbook = Workbook {
        path: path.to_string_lossy().into(),
        size_bytes: metadata.len(),
        owner: crate::file_facts::owner(path, &metadata),
        modified_unix_seconds: metadata
            .modified()
            .ok()
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_secs()),
        status: "inspected".into(),
        ..Workbook::default()
    };
    if bytes.starts_with(&[0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]) {
        read_vba(&bytes, &mut workbook, rules, weights, skip_protected)?;
    } else if bytes.starts_with(b"PK") {
        let mut zip = ZipArchive::new(Cursor::new(&bytes))?;
        let skipped = check_zip(&mut zip, true)?;
        if !skipped.is_empty() {
            add_feature(&mut workbook, "oversized_parts_uninspected");
            workbook.error = Some(skipped.join("; "));
        }
        let names: Vec<String> = zip.file_names().map(str::to_owned).collect();
        ensure!(
            names
                .iter()
                .any(|n| n == "xl/workbook.xml" || n == "xl/workbook.bin"),
            "ZIP is not an Excel workbook"
        );
        if names.iter().any(|n| n == "xl/workbook.bin") {
            add_feature(&mut workbook, "binary_features_uninspected");
        }
        for name in names {
            let lower = name.to_ascii_lowercase();
            if lower.starts_with("xl/activex/") && lower.ends_with(".bin") {
                add_feature(&mut workbook, "activex");
            }
            if lower.starts_with("xl/embeddings/") {
                add_feature(&mut workbook, "embedded_ole");
            }
            if lower.starts_with("xl/externallinks/") && !lower.contains("/_rels/") {
                add_feature(&mut workbook, "external_links");
            }
            if lower.starts_with("xl/model/") {
                add_feature(&mut workbook, "data_model");
            }
            if lower.starts_with("customui/") && lower.ends_with(".xml") {
                add_feature(&mut workbook, "ribbon");
            }
            if lower.contains("vbaprojectsignature") {
                add_feature(&mut workbook, "vba_signature");
            }
            if lower == "xl/connections.bin" {
                add_feature(&mut workbook, "external_connections");
            }
            // Oversized non-VBA parts are never decompressed or charged to the readable ZIP budget.
            let index = zip.index_for_name(&name).context("Missing ZIP entry")?;
            if zip.by_index_raw(index)?.size() > MAX_PART && !lower.ends_with("vbaproject.bin") {
                continue;
            }
            if lower.ends_with("vbaproject.bin") {
                read_vba(
                    &bounded_read(zip.by_name(&name)?, MAX_PART)?,
                    &mut workbook,
                    rules,
                    weights,
                    skip_protected,
                )?;
            } else if lower.ends_with(".xml")
                && (lower.starts_with("customxml/")
                    || lower == "xl/connections.xml"
                    || lower.starts_with("xl/drawings/")
                    || lower.starts_with("xl/worksheets/")
                    || lower.starts_with("customui/"))
            {
                let part = bounded_read(zip.by_name(&name)?, MAX_PART)?;
                for mashup in inspect_xml(&part, &mut workbook)
                    .with_context(|| format!("Reading XML part {name}"))?
                {
                    add_feature(&mut workbook, "power_query");
                    workbook
                        .queries
                        .extend(extract_mashup(&mashup).context("Reading Power Query")?);
                }
            } else if lower.ends_with(".vml") && lower.starts_with("xl/drawings/") {
                let part = xml_text(&bounded_read(zip.by_name(&name)?, MAX_PART)?)?;
                if let Err(error) = inspect_xml(part.as_bytes(), &mut workbook) {
                    // Legacy VML can contain HTML text; retain VBA and flag incomplete drawing coverage.
                    add_feature(&mut workbook, "vml_uninspected");
                    let warning = workbook.error.get_or_insert_with(String::new);
                    if !warning.is_empty() {
                        warning.push_str("; ");
                    }
                    warning.push_str(&format!(
                        "VML drawing {name} could not be fully inspected: {error}"
                    ));
                }
                if part.contains("FmlaMacro") {
                    add_feature(&mut workbook, "macro_assignment");
                }
            }
        }
    } else {
        bail!("Unrecognized workbook container (expected ZIP or CFB)");
    }
    workbook.features.sort();
    for rule in rules {
        if (rule.kind == "feature" && rule.pattern.iter().any(|p| workbook.features.contains(p)))
            || (rule.kind == "reference"
                && workbook.references.iter().any(|r| {
                    rule.pattern
                        .iter()
                        .any(|p| r.to_lowercase().contains(&p.to_lowercase()))
                }))
        {
            workbook.findings.push(rules::finding(rule, None));
        }
    }
    workbook.refresh_verdict();
    Ok(workbook)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    #[test]
    fn zip_budget_retains_aggregate_and_nested_part_limits() {
        let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
        for i in 0..17 {
            writer
                .start_file(
                    format!("part{i}.xml"),
                    zip::write::SimpleFileOptions::default(),
                )
                .unwrap();
        }
        let mut bytes = writer.finish().unwrap().into_inner();
        // Forge declared sizes to exercise metadata checks without expanding 272 MiB.
        let headers: Vec<_> = bytes
            .windows(4)
            .enumerate()
            .filter_map(|(i, signature)| (signature == b"PK\x01\x02").then_some(i))
            .collect();
        assert_eq!(headers.len(), 17);
        for header in &headers {
            bytes[header + 24..header + 28].copy_from_slice(&(MAX_PART as u32).to_le_bytes());
        }
        let mut zip = ZipArchive::new(Cursor::new(&bytes)).unwrap();
        assert!(
            check_zip(&mut zip, true)
                .unwrap_err()
                .to_string()
                .contains("aggregate scan limit")
        );
        for header in &headers {
            bytes[header + 24..header + 28].copy_from_slice(&((MAX_PART + 1) as u32).to_le_bytes());
        }
        let mut zip = ZipArchive::new(Cursor::new(&bytes)).unwrap();
        assert_eq!(check_zip(&mut zip, true).unwrap().len(), 17);
        assert!(
            check_zip(&mut zip, false)
                .unwrap_err()
                .to_string()
                .contains("per-part scan limit")
        );
    }
    #[test]
    fn reads_real_cmg_protection_record() {
        assert!(!project_protection("C4C6C19047EF4BEF4BEF4BEF4B").unwrap());
        assert!(project_protection("00020006040604010B010B").unwrap());
        assert!(project_protection("garbage").is_err());
        assert!(project_protection("C4C6C19047EF4B").is_err());
    }
    #[test]
    fn extracts_nested_query_and_rejects_truncation() {
        let mut zip = zip::ZipWriter::new(Cursor::new(Vec::new()));
        zip.start_file(
            "Formulas/Section1.m",
            zip::write::SimpleFileOptions::default(),
        )
        .unwrap();
        zip.write_all(b"section Section1; shared Budget = 42;")
            .unwrap();
        let package = zip.finish().unwrap().into_inner();
        let mut bytes = vec![0; 4];
        bytes.extend((package.len() as u32).to_le_bytes());
        bytes.extend(package);
        let queries = extract_mashup(&STANDARD.encode(&bytes)).unwrap();
        assert_eq!(
            queries[0].source.as_deref(),
            Some("section Section1; shared Budget = 42;")
        );
        bytes.pop();
        assert!(extract_mashup(&STANDARD.encode(bytes)).is_err());
    }
    #[test]
    fn reads_utf16_and_rejects_dtd() {
        let xml = "<root><connection/><shape macro=\"Run\"/></root>";
        let mut bytes = vec![0xff, 0xfe];
        bytes.extend(xml.encode_utf16().flat_map(u16::to_le_bytes));
        let mut workbook = Workbook::default();
        inspect_xml(&bytes, &mut workbook).unwrap();
        assert!(workbook.features.contains(&"external_connections".into()));
        assert!(workbook.features.contains(&"macro_assignment".into()));
        assert!(inspect_xml(b"<!DOCTYPE root><root/>", &mut workbook).is_err());
    }
}
