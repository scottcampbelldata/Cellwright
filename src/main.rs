// SPDX-License-Identifier: EUPL-1.2
use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand, ValueEnum};
use macroferry::{container, model::Workbook, report, rules, scan};
use std::{
    io::{Read, Write},
    path::PathBuf,
    process::Command,
    time::Duration,
};

#[derive(Parser)]
#[command(
    version,
    about = "Offline Excel VBA inventory and migration assessment"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Scan files or folders and write offline HTML, CSV and JSON reports
    Scan(ScanArgs),
    /// Extract VBA source and Power Query M sections into new text files
    Extract(ScanArgs),
    /// Create a migration candidate with source diffs and TODOs (requires Python)
    Convert {
        path: PathBuf,
        #[arg(long)]
        out: PathBuf,
        #[arg(long, default_value = "basic")]
        target: String,
        #[arg(long)]
        libreoffice: Option<PathBuf>,
    },
    /// Open the local migration dashboard (requires Python)
    Serve {
        #[arg(long, default_value_t = 8768)]
        port: u16,
        #[arg(long, default_value = "reports/dashboard")]
        data: PathBuf,
    },
    /// Capture, compare or run converted macros using the Python migration tools
    Migrate {
        #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
        args: Vec<String>,
    },
    /// Inspect the assessment rules
    Rules {
        #[command(subcommand)]
        command: RuleCommands,
    },
    #[command(name = "__inspect", hide = true)]
    Inspect(InspectArgs),
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum Language {
    En,
    Fr,
    De,
}
impl Language {
    fn code(self) -> &'static str {
        match self {
            Self::En => "en",
            Self::Fr => "fr",
            Self::De => "de",
        }
    }
}

#[derive(Args)]
struct ScanArgs {
    /// Files, directories or UNC shares; directory traversal skips symbolic links
    #[arg(required = true)]
    paths: Vec<PathBuf>,
    /// New or empty destination directory
    #[arg(long, default_value = "reports")]
    out: PathBuf,
    /// Exclude VBA and M source from every report (paths and findings remain)
    #[arg(long)]
    no_source: bool,
    /// Skip protected VBA projects, including unknown protection states
    #[arg(long)]
    skip_protected: bool,
    /// TOML rule additions or overrides by rule ID
    #[arg(long)]
    rules: Option<PathBuf>,
    /// TOML estimate weights
    #[arg(long)]
    weights: Option<PathBuf>,
    #[arg(long, value_enum, default_value = "en")]
    lang: Language,
    /// Concurrent isolated workbook processes
    #[arg(long, default_value_t = 2, value_parser = clap::value_parser!(u16).range(1..=32))]
    jobs: u16,
    /// Time budget per workbook in seconds
    #[arg(long, default_value_t = 15, value_parser = clap::value_parser!(u16).range(1..=3600))]
    timeout: u16,
}

#[derive(Subcommand)]
enum RuleCommands {
    /// List the built-in rules, optionally applying a TOML override
    List {
        #[arg(long)]
        rules: Option<PathBuf>,
        #[arg(long, value_enum, default_value = "en")]
        lang: Language,
    },
}

#[derive(Args)]
struct InspectArgs {
    path: PathBuf,
    #[arg(long)]
    rules: Option<PathBuf>,
    #[arg(long)]
    weights: Option<PathBuf>,
    #[arg(long)]
    no_source: bool,
    #[arg(long)]
    skip_protected: bool,
    #[arg(long)]
    config_stdin: bool,
}

fn worker(args: InspectArgs) -> Result<()> {
    let (rules, weights) = if args.config_stdin {
        let mut bytes = Vec::new();
        std::io::stdin()
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        anyhow::ensure!(
            bytes.len() <= 16 * 1024 * 1024,
            "Worker configuration exceeds limit"
        );
        serde_json::from_slice::<(Vec<rules::Rule>, rules::Weights)>(&bytes)?
    } else {
        (
            rules::load(args.rules.as_deref())?,
            rules::Weights::load(args.weights.as_deref())?,
        )
    };
    let result = std::panic::catch_unwind(|| {
        container::inspect(&args.path, &rules, &weights, args.skip_protected)
    });
    let mut workbook = match result {
        Ok(Ok(w)) => w,
        Ok(Err(e)) => Workbook {
            path: args.path.to_string_lossy().into(),
            size_bytes: std::fs::metadata(&args.path).map(|m| m.len()).unwrap_or(0),
            status: "error".into(),
            error: Some(format!("{e:#}")),
            ..Workbook::default()
        },
        Err(_) => Workbook {
            path: args.path.to_string_lossy().into(),
            status: "error".into(),
            error: Some("Workbook parser panicked; inspection isolated".into()),
            ..Workbook::default()
        },
    };
    if args.no_source {
        workbook.remove_source();
    }
    serde_json::to_writer(std::io::stdout().lock(), &workbook)?;
    Ok(())
}

fn run_scan(args: ScanArgs, extract: bool) -> Result<bool> {
    anyhow::ensure!(
        !extract || !args.no_source,
        "extract cannot be combined with --no-source"
    );
    let rules = rules::load(args.rules.as_deref())?;
    let weights = rules::Weights::load(args.weights.as_deref())?;
    scan::prepare_output(&args.out)?;
    let options = scan::Options {
        jobs: args.jobs.into(),
        timeout: Duration::from_secs(args.timeout.into()),
        no_source: args.no_source,
        skip_protected: args.skip_protected,
    };
    let scan = scan::run(&args.paths, &options, rules, weights, args.lang.code())?;
    report::write(&scan, &args.out)?;
    if extract {
        report::extract(&scan, &args.out.join("extract"))?;
    }
    let failed = scan
        .workbooks
        .iter()
        .filter(|w| w.status != "inspected")
        .count();
    eprintln!(
        "{} workbook(s), {} uninspected, {} discovery error(s), {} unique module(s). Reports: {}",
        scan.workbooks.len(),
        failed,
        scan.discovery_errors.len(),
        scan.unique_modules,
        args.out.display()
    );
    Ok(failed == 0 && scan.discovery_errors.is_empty())
}

fn run() -> Result<bool> {
    match Cli::parse().command {
        Commands::Scan(args) => run_scan(args, false),
        Commands::Extract(args) => run_scan(args, true),
        Commands::Convert {
            path,
            out,
            target,
            libreoffice,
        } => {
            let mut args = vec![
                "convert".into(),
                path.to_string_lossy().into_owned(),
                "--out".into(),
                out.to_string_lossy().into_owned(),
                "--target".into(),
                target,
                "--binary".into(),
                std::env::current_exe()?.to_string_lossy().into_owned(),
            ];
            if let Some(path) = libreoffice {
                args.extend(["--libreoffice".into(), path.to_string_lossy().into_owned()]);
            }
            run_python("migration", &args)
        }
        Commands::Serve { port, data } => run_python(
            "dashboard.server",
            &[
                "--port".into(),
                port.to_string(),
                "--data".into(),
                data.to_string_lossy().into_owned(),
                "--binary".into(),
                std::env::current_exe()?.to_string_lossy().into_owned(),
            ],
        ),
        Commands::Migrate { args } => run_python("migration", &args),
        Commands::Inspect(args) => {
            worker(args)?;
            Ok(true)
        }
        Commands::Rules {
            command: RuleCommands::List { rules: path, lang },
        } => {
            let index = report::language_index(lang.code());
            let mut stdout = std::io::stdout().lock();
            for rule in rules::load(path.as_deref())? {
                writeln!(
                    stdout,
                    "{}\t{}\t{}\t{}",
                    rule.id,
                    rule.category,
                    rule.verdict.key(),
                    rule.messages[index]
                )?;
            }
            Ok(true)
        }
    }
}

fn run_python(module: &str, args: &[String]) -> Result<bool> {
    let executable = std::env::current_exe()?;
    let bundled = executable
        .parent()
        .context("Executable directory unavailable")?;
    let root = bundled
        .ancestors()
        .find(|path| path.join("migration/__init__.py").is_file())
        .context("Migration tools are missing; use the full distribution archive")?;
    let python = std::env::var_os("MACROFERRY_PYTHON").unwrap_or_else(|| "python".into());
    let mut search_path = vec![root.to_path_buf()];
    if let Some(existing) = std::env::var_os("PYTHONPATH") {
        search_path.extend(std::env::split_paths(&existing));
    }
    let status = Command::new(python)
        .args(["-m", module])
        .args(args)
        .env("PYTHONPATH", std::env::join_paths(search_path)?)
        .status()
        .context("Starting Python tools; install Python 3.11+ or set MACROFERRY_PYTHON")?;
    Ok(status.success())
}

fn main() {
    match run().context("MacroFerry failed") {
        Ok(true) => (),
        Ok(false) => std::process::exit(1),
        Err(e) => {
            eprintln!("{e:#}");
            std::process::exit(2);
        }
    }
}
