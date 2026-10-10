// SPDX-License-Identifier: EUPL-1.2
use crate::{
    model::{DuplicateGroup, DuplicateMember, Scan, Workbook},
    rules::{Rule, Weights},
};
use anyhow::{Context, Result, ensure};
use rayon::prelude::*;
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use walkdir::WalkDir;

pub fn is_workbook(path: &Path) -> bool {
    path.extension().and_then(|e| e.to_str()).is_some_and(|e| {
        ["xlsm", "xlsb", "xls", "xlam", "xla", "xltm", "xlsx"]
            .contains(&e.to_ascii_lowercase().as_str())
    })
}

pub fn discover(paths: &[PathBuf]) -> (Vec<PathBuf>, Vec<String>) {
    let mut files = BTreeSet::new();
    let mut errors = Vec::new();
    for path in paths {
        let path = match std::fs::canonicalize(path) {
            Ok(p) => p,
            Err(e) => {
                errors.push(format!("{}: {e}", path.display()));
                continue;
            }
        };
        if path.is_file() {
            if is_workbook(&path) {
                files.insert(path);
            } else {
                errors.push(format!(
                    "Unsupported workbook extension: {}",
                    path.display()
                ));
            }
        } else {
            for entry in WalkDir::new(&path).follow_links(false) {
                match entry {
                    Ok(e) if e.file_type().is_file() && is_workbook(e.path()) => {
                        files.insert(e.path().to_owned());
                    }
                    Ok(_) => (),
                    Err(e) => errors.push(e.to_string()),
                }
            }
        }
    }
    (files.into_iter().collect(), errors)
}

pub struct Options {
    pub jobs: usize,
    pub timeout: Duration,
    pub no_source: bool,
    pub skip_protected: bool,
}

fn isolated_inspect(path: &Path, options: &Options, configuration: &[u8]) -> Result<Workbook> {
    let mut command = Command::new(std::env::current_exe()?);
    command
        .arg("__inspect")
        .arg(path)
        .arg("--config-stdin")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    if options.no_source {
        command.arg("--no-source");
    }
    if options.skip_protected {
        command.arg("--skip-protected");
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // Avoid opening a console for each workbook.
    }
    let mut child = command
        .spawn()
        .context("Starting workbook inspection process")?;
    if let Err(error) = child
        .stdin
        .take()
        .context("Missing worker configuration input")?
        .write_all(configuration)
    {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error.into());
    }
    let stdout = child.stdout.take().context("Missing worker stdout")?;
    // Drain concurrently so a report larger than the pipe buffer cannot deadlock the worker.
    let reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout
            .take(64 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map(|_| bytes)
    });
    let start = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) if start.elapsed() < options.timeout => {
                thread::sleep(Duration::from_millis(20))
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(anyhow::anyhow!(
                    "Workbook exceeded {} second inspection budget",
                    options.timeout.as_secs()
                ));
            }
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(e.into());
            }
        }
    };
    let bytes = reader
        .join()
        .map_err(|_| anyhow::anyhow!("Inspection output reader failed"))??;
    ensure!(status?.success(), "Inspection process crashed or failed");
    ensure!(
        bytes.len() <= 64 * 1024 * 1024,
        "Inspection output exceeded 64 MiB limit"
    );
    serde_json::from_slice(&bytes).context("Invalid inspection output")
}

pub fn run(
    paths: &[PathBuf],
    options: &Options,
    rules: Vec<Rule>,
    weights: Weights,
    language: &str,
) -> Result<Scan> {
    let (files, discovery_errors) = discover(paths);
    let configuration = serde_json::to_vec(&(&rules, &weights))?;
    ensure!(
        configuration.len() <= 16 * 1024 * 1024,
        "Rule configuration exceeds 16 MiB"
    );
    eprintln!(
        "Found {} workbook(s); inspecting with {} worker(s)",
        files.len(),
        options.jobs
    );
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(options.jobs)
        .build()?;
    let workbooks: Vec<Workbook> = pool.install(|| {
        files
            .par_iter()
            .map(
                |path| match isolated_inspect(path, options, &configuration) {
                    Ok(w) => w,
                    Err(e) => Workbook {
                        path: path.to_string_lossy().into(),
                        size_bytes: std::fs::metadata(path).map(|m| m.len()).unwrap_or(0),
                        status: "error".into(),
                        error: Some(format!("{e:#}")),
                        ..Workbook::default()
                    },
                },
            )
            .collect()
    });
    let mut groups = BTreeMap::<String, Vec<DuplicateMember>>::new();
    let mut unique_hours = BTreeMap::<String, f64>::new();
    let mut feature_hours = 0.0;
    for workbook in &workbooks {
        feature_hours +=
            weights.finding_hours(&workbook.findings) + weights.userform_hours(&workbook.forms);
        for module in &workbook.modules {
            if module.code_lines == 0 {
                continue;
            }
            groups
                .entry(module.normalized_sha256.clone())
                .or_default()
                .push(DuplicateMember {
                    workbook: workbook.path.clone(),
                    module: module.name.clone(),
                });
            unique_hours
                .entry(module.normalized_sha256.clone())
                .or_insert(module.estimated_hours);
        }
    }
    let hours: f64 = unique_hours.values().sum::<f64>() + feature_hours;
    let duplicates = groups
        .into_iter()
        .filter(|(_, members)| members.len() > 1)
        .map(|(hash, members)| DuplicateGroup { hash, members })
        .collect();
    Ok(Scan {
        schema_version: "0.1".into(),
        tool_version: env!("CARGO_PKG_VERSION").into(),
        generated_unix_seconds: SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs(),
        language: language.into(),
        source_included: !options.no_source,
        rules,
        estimate: weights.clone(),
        unique_modules: unique_hours.len(),
        estimated_hours_low: hours * weights.low_multiplier,
        estimated_hours_high: hours * weights.high_multiplier,
        discovery_errors,
        duplicates,
        workbooks,
    })
}

pub fn prepare_output(path: &Path) -> Result<()> {
    if path.exists() {
        ensure!(
            path.is_dir() && std::fs::read_dir(path)?.next().is_none(),
            "Output directory must be new or empty: {}",
            path.display()
        );
    } else {
        std::fs::create_dir_all(path)
            .with_context(|| format!("Creating output {}", path.display()))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn discovers_recursively_and_deduplicates_inputs() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("nested")).unwrap();
        let workbook = dir.path().join("nested/BUDGET.XLSM");
        std::fs::write(&workbook, b"fixture").unwrap();
        std::fs::write(dir.path().join("notes.txt"), b"text").unwrap();
        let (files, errors) = discover(&[dir.path().into(), workbook]);
        assert_eq!(files.len(), 1);
        assert!(errors.is_empty());
        assert!(prepare_output(dir.path()).is_err());
    }
}
