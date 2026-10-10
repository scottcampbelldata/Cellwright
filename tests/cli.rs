// SPDX-License-Identifier: EUPL-1.2
use serde_json::Value;
use std::{
    fs,
    io::{Cursor, Read, Write},
    path::{Path, PathBuf},
    process::{Command, Output},
};
use zip::{ZipWriter, write::SimpleFileOptions};

fn cli(args: &[&str], input: &Path, out: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_cellwright"))
        .args(args)
        .arg(input)
        .arg("--out")
        .arg(out)
        .output()
        .unwrap()
}
fn corpus(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("corpus")
        .join(name)
}

#[cfg(unix)]
#[test]
fn python3_fallback_and_dashboard_execution_flag() {
    use std::os::unix::fs::PermissionsExt;
    let temp = tempfile::tempdir().unwrap();
    let binary = temp.path().join("cellwright");
    fs::copy(env!("CARGO_BIN_EXE_cellwright"), &binary).unwrap();
    fs::create_dir(temp.path().join("migration")).unwrap();
    fs::write(temp.path().join("migration/__init__.py"), "").unwrap();
    let python3 = temp.path().join("python3");
    fs::write(&python3, "#!/bin/sh\nprintf 'python3 %s\\n' \"$*\"\n").unwrap();
    fs::set_permissions(&python3, fs::Permissions::from_mode(0o755)).unwrap();
    let run = |args: &[&str], override_python: Option<&Path>| {
        let mut command = Command::new(&binary);
        command
            .args(args)
            .env("PATH", temp.path())
            .env_remove("CELLWRIGHT_PYTHON");
        if let Some(path) = override_python {
            command.env("CELLWRIGHT_PYTHON", path);
        }
        command.output().unwrap()
    };
    let result = run(&["migrate", "compare", "--help"], None);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(
        String::from_utf8_lossy(&result.stdout).contains("python3 -m migration compare --help")
    );
    let result = run(&["serve", "--allow-execution"], None);
    assert!(result.status.success());
    assert!(String::from_utf8_lossy(&result.stdout).contains("--allow-execution"));
    let result = run(&["serve", "--open"], None);
    assert!(String::from_utf8_lossy(&result.stdout).contains("--open"));
    assert!(!String::from_utf8_lossy(&result.stdout).contains("--allow-execution"));
    let result = run(
        &["migrate", "compare", "--help"],
        Some(&temp.path().join("missing-python")),
    );
    assert_eq!(result.status.code(), Some(2));
    assert!(!String::from_utf8_lossy(&result.stdout).contains("python3"));
    let python = temp.path().join("python");
    fs::write(&python, "#!/bin/sh\nprintf 'first-python\\n'\nexit 42\n").unwrap();
    fs::set_permissions(&python, fs::Permissions::from_mode(0o755)).unwrap();
    let result = run(&["migrate", "compare", "--help"], None);
    assert_eq!(result.status.code(), Some(1));
    assert_eq!(
        String::from_utf8_lossy(&result.stdout).trim(),
        "first-python"
    );
}

#[test]
fn controlled_workbooks_inventory_code_page_owner_and_real_query() {
    let rules = cellwright::rules::load(None).unwrap();
    let weights = cellwright::rules::Weights::default();
    let book = cellwright::container::inspect(
        &corpus("generated/arithmetic-source-only.xlsm"),
        &rules,
        &weights,
        false,
    )
    .unwrap();
    assert_eq!(book.code_page, Some(1252));
    assert!(book.owner.as_ref().is_some_and(|value| !value.is_empty()));
    assert!(book.modules.iter().any(|module| {
        module.name == "Arithmetic"
            && module
                .source
                .as_deref()
                .is_some_and(|source| source.contains("Sub Calculate"))
    }));
    let book = cellwright::container::inspect(
        &corpus("generated/sales-query.xlsx"),
        &rules,
        &weights,
        false,
    )
    .unwrap();
    assert_eq!(book.queries.len(), 1);
    assert!(book.queries[0].names.contains(&"Sales".to_string()));
    assert!(book.queries[0].steps.contains(&"Grouped".to_string()));
    assert!(!book.connections.is_empty());
}
fn json(out: &Path) -> Value {
    serde_json::from_slice(&fs::read(out.join("scan.json")).unwrap()).unwrap()
}

#[test]
fn real_vba_extract_and_private_reports() {
    let temp = tempfile::tempdir().unwrap();
    let out = temp.path().join("extract-report");
    let input = corpus("calamine-vba.xlsm");
    let before = fs::read(&input).unwrap();
    let result = cli(&["extract"], &input, &out);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let scan = json(&out);
    let workbook = &scan["workbooks"][0];
    assert_eq!(workbook["protected"], false);
    assert_eq!(workbook["modules"].as_array().unwrap().len(), 5);
    assert_eq!(scan["unique_modules"], 1);
    let module = workbook["modules"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["name"] == "testVBA")
        .unwrap();
    assert!(
        module["source"]
            .as_str()
            .unwrap()
            .contains("Hello from vba!")
    );
    let manifest: Value =
        serde_json::from_slice(&fs::read(out.join("extract/manifest.json")).unwrap()).unwrap();
    assert_eq!(manifest.as_array().unwrap().len(), 5);
    for entry in manifest.as_array().unwrap() {
        assert!(
            out.join("extract")
                .join(entry["file"].as_str().unwrap())
                .is_file()
        );
    }
    assert_eq!(fs::read(&input).unwrap(), before);
    let private = temp.path().join("private");
    assert!(
        cli(
            &["scan", "--no-source", "--lang", "fr", "--skip-protected"],
            &input,
            &private
        )
        .status
        .success()
    );
    let private_scan = json(&private);
    assert_eq!(private_scan["source_included"], false);
    for module in private_scan["workbooks"][0]["modules"].as_array().unwrap() {
        assert!(module.get("source").is_none());
    }
    for file in [
        "scan.json",
        "report.html",
        "workbooks.csv",
        "modules.csv",
        "findings.csv",
    ] {
        assert!(
            !fs::read_to_string(private.join(file))
                .unwrap()
                .contains("Hello from vba!")
        );
    }
    assert!(
        fs::read_to_string(private.join("report.html"))
            .unwrap()
            .contains("lang=\"fr\"")
    );
    let original_report = fs::read(private.join("report.html")).unwrap();
    assert_eq!(cli(&["scan"], &input, &private).status.code(), Some(2));
    assert_eq!(
        fs::read(private.join("report.html")).unwrap(),
        original_report
    );
}

#[test]
fn encrypted_corrupt_and_duplicate_workbooks() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("input");
    fs::create_dir(&input).unwrap();
    fs::copy(corpus("calamine-vba.xlsm"), input.join("first.xlsm")).unwrap();
    fs::copy(corpus("calamine-vba.xlsm"), input.join("copy.xlsm")).unwrap();
    fs::copy(corpus("encrypted.xlsb"), input.join("encrypted.xlsb")).unwrap();
    fs::write(input.join("corrupt.XLS"), b"broken container").unwrap();
    let out = temp.path().join("reports");
    let result = cli(&["scan", "--no-source"], &input, &out);
    assert_eq!(result.status.code(), Some(1));
    let scan = json(&out);
    assert_eq!(scan["workbooks"].as_array().unwrap().len(), 4);
    assert!(
        scan["workbooks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|w| w["status"] == "encrypted" && w["verdict"] == "unknown")
    );
    assert!(
        scan["workbooks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|w| w["status"] == "error")
    );
    assert_eq!(scan["unique_modules"], 1);
    assert_eq!(scan["duplicates"].as_array().unwrap().len(), 1);
    assert_eq!(
        scan["duplicates"][0]["members"].as_array().unwrap().len(),
        2
    );
}

fn write_zip(path: &Path, entries: &[(&str, &[u8])]) {
    let mut zip = ZipWriter::new(fs::File::create(path).unwrap());
    for (name, bytes) in entries {
        zip.start_file(*name, SimpleFileOptions::default()).unwrap();
        zip.write_all(bytes).unwrap();
    }
    zip.finish().unwrap();
}

#[test]
fn feature_inventory_and_query_privacy() {
    use base64::Engine;
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("features.xlsx");
    let mut package = ZipWriter::new(Cursor::new(Vec::new()));
    package
        .start_file("Formulas/Section1.m", SimpleFileOptions::default())
        .unwrap();
    package
        .write_all(b"section Section1; shared Secret = File.Contents(\"SECRET_SOURCE.csv\");")
        .unwrap();
    let package = package.finish().unwrap().into_inner();
    let mut mashup = vec![0; 4];
    mashup.extend((package.len() as u32).to_le_bytes());
    mashup.extend(package);
    let xml = format!(
        "<DataMashup xmlns=\"http://schemas.microsoft.com/DataMashup\">{}</DataMashup>",
        base64::engine::general_purpose::STANDARD.encode(mashup)
    );
    let mut xml16 = vec![0xff, 0xfe];
    xml16.extend(xml.encode_utf16().flat_map(u16::to_le_bytes));
    write_zip(
        &input,
        &[
            ("xl/workbook.xml", b"<workbook/>"),
            ("customXml/item2.xml", &xml16),
            (
                "xl/connections.xml",
                b"<connections><connection id=\"1\"/></connections>",
            ),
            ("xl/activeX/activeX1.bin", b"control"),
            ("xl/externalLinks/externalLink1.xml", b"<externalLink/>"),
            ("xl/drawings/drawing1.xml", b"<shape macro=\"Run\"/>"),
            ("xl/model/item.data", b"model"),
            ("customUI/customUI.xml", b"<customUI/>"),
            ("xl/embeddings/object.bin", b"OLE"),
        ],
    );
    let out = temp.path().join("reports");
    assert!(cli(&["scan", "--no-source"], &input, &out).status.success());
    let scan = json(&out);
    let features = scan["workbooks"][0]["features"].as_array().unwrap();
    for feature in [
        "power_query",
        "external_connections",
        "external_links",
        "activex",
        "data_model",
        "macro_assignment",
        "ribbon",
        "embedded_ole",
    ] {
        assert!(features.contains(&Value::String(feature.into())));
    }
    assert_eq!(scan["workbooks"][0]["queries"].as_array().unwrap().len(), 1);
    assert!(scan["workbooks"][0]["queries"][0].get("source").is_none());
    assert!(
        !fs::read_to_string(out.join("scan.json"))
            .unwrap()
            .contains("SECRET_SOURCE")
    );
    let extract_out = temp.path().join("extraction");
    assert!(cli(&["extract"], &input, &extract_out).status.success());
    let manifest: Value =
        serde_json::from_slice(&fs::read(extract_out.join("extract/manifest.json")).unwrap())
            .unwrap();
    let path = manifest[0]["file"].as_str().unwrap();
    assert!(
        fs::read_to_string(extract_out.join("extract").join(path))
            .unwrap()
            .contains("SECRET_SOURCE")
    );
}

#[test]
fn malformed_legacy_vml_retains_vba_with_unknown_drawing_coverage() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("legacy-drawing.xlsm");
    let vba = public_vba_bytes();
    write_zip(
        &input,
        &[
            ("xl/workbook.xml", b"<workbook/>"),
            ("xl/vbaProject.bin", &vba),
            (
                "xl/drawings/vmlDrawing1.vml",
                b"<xml><font><br></font><FmlaMacro>Run</FmlaMacro></xml>",
            ),
        ],
    );
    let output = temp.path().join("report");
    assert!(
        cli(&["scan", "--no-source"], &input, &output)
            .status
            .success()
    );
    let scan = json(&output);
    let book = &scan["workbooks"][0];
    assert_eq!(book["status"], "inspected");
    assert_eq!(book["modules"].as_array().unwrap().len(), 5);
    assert_eq!(book["verdict"], "unknown");
    assert!(book["error"].as_str().unwrap().contains("vmlDrawing1.vml"));
    assert!(
        book["features"]
            .as_array()
            .unwrap()
            .contains(&Value::String("vml_uninspected".into()))
    );
    assert!(
        book["features"]
            .as_array()
            .unwrap()
            .contains(&Value::String("macro_assignment".into()))
    );
    assert!(
        book["findings"]
            .as_array()
            .unwrap()
            .iter()
            .any(|finding| finding["rule_id"] == "MF060")
    );
    let strict = temp.path().join("bad-worksheet.xlsm");
    write_zip(
        &strict,
        &[
            ("xl/workbook.xml", b"<workbook/>"),
            ("xl/vbaProject.bin", &vba),
            ("xl/worksheets/sheet1.xml", b"<worksheet><row></worksheet>"),
        ],
    );
    let output = temp.path().join("strict-report");
    assert_eq!(cli(&["scan"], &strict, &output).status.code(), Some(1));
    assert_eq!(json(&output)["workbooks"][0]["status"], "error");
}

#[test]
fn rejects_archive_bombs_and_missing_inputs() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("oversized.xlsx");
    let oversized = vec![b'x'; cellwright::container::MAX_PART as usize + 1];
    let mut zip = ZipWriter::new(fs::File::create(&input).unwrap());
    zip.start_file("xl/workbook.xml", SimpleFileOptions::default())
        .unwrap();
    zip.write_all(b"<workbook/>").unwrap();
    zip.start_file(
        "xl/vbaProject.bin",
        SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
    )
    .unwrap();
    zip.write_all(&oversized).unwrap();
    zip.finish().unwrap();
    let out = temp.path().join("reports");
    assert_eq!(cli(&["scan"], &input, &out).status.code(), Some(1));
    let scan = json(&out);
    let book = &scan["workbooks"][0];
    assert_eq!(book["status"], "error");
    assert_eq!(book["verdict"], "unknown");
    assert!(book["modules"].as_array().unwrap().is_empty());
    let error = book["error"].as_str().unwrap();
    assert!(error.contains("xl/vbaProject.bin"));
    assert!(error.contains(&oversized.len().to_string()));
    assert!(error.contains("16 MiB per-part scan limit"));
    assert!(error.contains("archive too large to inspect"));
    assert_eq!(scan["estimated_hours_low"], 0.0);
    assert_eq!(scan["estimated_hours_high"], 0.0);
    assert!(
        fs::read_to_string(out.join("report.html"))
            .unwrap()
            .contains("archive too large to inspect")
    );
    let out = temp.path().join("missing");
    assert_eq!(
        cli(&["scan"], &temp.path().join("missing.xlsm"), &out)
            .status
            .code(),
        Some(1)
    );
    assert_eq!(json(&out)["discovery_errors"].as_array().unwrap().len(), 1);
    assert_eq!(
        cli(
            &["extract", "--no-source"],
            &corpus("calamine-vba.xlsm"),
            &temp.path().join("invalid")
        )
        .status
        .code(),
        Some(2)
    );
}

#[test]
fn oversized_non_vba_parts_retain_vba_and_flag_unknown_coverage() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("large-worksheet.xlsm");
    let vba = public_vba_bytes();
    let mut zip = ZipWriter::new(fs::File::create(&input).unwrap());
    for (name, bytes) in [
        ("xl/workbook.xml", b"<workbook/>".as_slice()),
        ("xl/vbaProject.bin", &vba),
    ] {
        zip.start_file(name, SimpleFileOptions::default()).unwrap();
        zip.write_all(bytes).unwrap();
    }
    let oversized = vec![0xff; cellwright::container::MAX_PART as usize + 1];
    for name in [
        "xl/worksheets/sheet1.xml",
        "xl/calcChain.xml",
        "xl/activeX/activeX1.bin",
    ] {
        zip.start_file(
            name,
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )
        .unwrap();
        zip.write_all(&oversized).unwrap();
    }
    zip.start_file("xl/drawings/vmlDrawing1.vml", SimpleFileOptions::default())
        .unwrap();
    zip.write_all(b"<xml><br></xml>").unwrap();
    zip.finish().unwrap();
    let output = temp.path().join("report");
    let result = cli(&["scan", "--no-source"], &input, &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let scan = json(&output);
    let book = &scan["workbooks"][0];
    assert_eq!(book["status"], "inspected");
    assert_eq!(book["verdict"], "unknown");
    assert_eq!(book["modules"].as_array().unwrap().len(), 5);
    assert!(
        book["modules"]
            .as_array()
            .unwrap()
            .iter()
            .all(|module| module.get("source").is_none())
    );
    let warning = book["error"].as_str().unwrap();
    for part in [
        "sheet1.xml",
        "calcChain.xml",
        "activeX1.bin",
        "vmlDrawing1.vml",
        "16 MiB",
        "16777217",
    ] {
        assert!(warning.contains(part), "{warning}");
    }
    for feature in ["oversized_parts_uninspected", "activex", "vml_uninspected"] {
        assert!(
            book["features"]
                .as_array()
                .unwrap()
                .contains(&Value::String(feature.into()))
        );
    }
    assert!(
        book["findings"]
            .as_array()
            .unwrap()
            .iter()
            .any(|finding| finding["rule_id"] == "MF060")
    );
    assert!(scan["estimated_hours_low"].as_f64().unwrap() > 0.0);
}

#[test]
fn public_sources_match_independent_olevba_hashes() {
    use sha2::{Digest, Sha256};
    let expected: Value = serde_json::from_str(include_str!("../corpus/expected.json")).unwrap();
    let rules = cellwright::rules::load(None).unwrap();
    let weights = cellwright::rules::Weights::default();
    for fixture in expected.as_array().unwrap() {
        let file = corpus(fixture["file"].as_str().unwrap());
        let hash: String = Sha256::digest(fs::read(&file).unwrap())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(hash, fixture["sha256"]);
        let Some(expected_modules) = fixture.get("modules") else {
            continue;
        };
        let workbook = cellwright::container::inspect(&file, &rules, &weights, false).unwrap();
        assert_eq!(
            workbook.modules.len(),
            expected_modules.as_array().unwrap().len()
        );
        for module in expected_modules.as_array().unwrap() {
            let actual = workbook
                .modules
                .iter()
                .find(|m| m.name == module["name"].as_str().unwrap())
                .unwrap();
            let source = actual
                .source
                .as_ref()
                .unwrap()
                .replace("\r\n", "\n")
                .replace('\r', "\n");
            let hash: String = Sha256::digest(source.as_bytes())
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect();
            assert_eq!(hash, module["source_sha256"]);
            assert_eq!(actual.lines, module["lines"].as_u64().unwrap() as usize);
        }
    }
}

fn public_vba_bytes() -> Vec<u8> {
    let mut zip =
        zip::ZipArchive::new(fs::File::open(corpus("calamine-vba.xlsm")).unwrap()).unwrap();
    let mut bytes = Vec::new();
    zip.by_name("xl/vbaProject.bin")
        .unwrap()
        .read_to_end(&mut bytes)
        .unwrap();
    bytes
}

#[test]
fn protected_project_is_omitted_when_requested() {
    let temp = tempfile::tempdir().unwrap();
    let mut cfb = cfb::CompoundFile::open(Cursor::new(public_vba_bytes())).unwrap();
    let mut project = String::new();
    cfb.open_stream("/PROJECT")
        .unwrap()
        .read_to_string(&mut project)
        .unwrap();
    project = project.replace("C4C6C19047EF4BEF4BEF4BEF4B", "00020006040604010B010B");
    cfb.create_stream("/PROJECT")
        .unwrap()
        .write_all(project.as_bytes())
        .unwrap();
    let bytes = cfb.into_inner().into_inner();
    let input = temp.path().join("protected.xlsm");
    write_zip(
        &input,
        &[
            ("xl/workbook.xml", b"<workbook/>"),
            ("xl/vbaProject.bin", &bytes),
        ],
    );
    let out = temp.path().join("skipped");
    assert_eq!(
        cli(&["scan", "--skip-protected"], &input, &out)
            .status
            .code(),
        Some(1)
    );
    let report = json(&out);
    assert_eq!(report["workbooks"][0]["protected"], true);
    assert_eq!(report["workbooks"][0]["status"], "skipped_protected");
    assert!(
        report["workbooks"][0]["modules"]
            .as_array()
            .unwrap()
            .is_empty()
    );
    let out = temp.path().join("included");
    assert!(cli(&["scan"], &input, &out).status.success());
    assert_eq!(
        json(&out)["workbooks"][0]["modules"]
            .as_array()
            .unwrap()
            .len(),
        5
    );
}

#[test]
fn legacy_and_binary_containers_extract_vba_with_coverage_warning() {
    let temp = tempfile::tempdir().unwrap();
    let bytes = public_vba_bytes();
    let rules = cellwright::rules::load(None).unwrap();
    let weights = cellwright::rules::Weights::default();
    let binary = temp.path().join("synthetic.xlsb");
    write_zip(
        &binary,
        &[
            ("xl/workbook.bin", b"synthetic marker"),
            ("xl/vbaProject.bin", &bytes),
        ],
    );
    let workbook = cellwright::container::inspect(&binary, &rules, &weights, false).unwrap();
    assert_eq!(workbook.modules.len(), 5);
    assert_eq!(workbook.verdict, cellwright::model::Verdict::Unknown);
    let mut source = cfb::CompoundFile::open(Cursor::new(bytes)).unwrap();
    let entries: Vec<_> = source
        .walk()
        .map(|e| (e.path().to_owned(), e.is_storage()))
        .collect();
    let legacy = temp.path().join("synthetic.xls");
    let mut target = cfb::CompoundFile::create_with_version(
        cfb::Version::V4,
        fs::File::create(&legacy).unwrap(),
    )
    .unwrap();
    target.create_storage("/_VBA_PROJECT_CUR").unwrap();
    target
        .create_stream("/Workbook")
        .unwrap()
        .write_all(b"synthetic marker")
        .unwrap();
    for (path, storage) in entries {
        if path == Path::new("/") {
            continue;
        }
        let destination = Path::new("/_VBA_PROJECT_CUR").join(path.strip_prefix("/").unwrap());
        if storage {
            target.create_storage_all(destination).unwrap();
        } else {
            let mut contents = Vec::new();
            source
                .open_stream(&path)
                .unwrap()
                .read_to_end(&mut contents)
                .unwrap();
            target
                .create_stream(destination)
                .unwrap()
                .write_all(&contents)
                .unwrap();
        }
    }
    drop(target);
    let workbook = cellwright::container::inspect(&legacy, &rules, &weights, false).unwrap();
    assert_eq!(workbook.modules.len(), 5);
    assert_eq!(workbook.verdict, cellwright::model::Verdict::Unknown);
}
