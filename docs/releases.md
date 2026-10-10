# Local builds and release preparation

Rust 1.99.0 and Cargo.lock pin the native build. Full archives include the native scanner, Python tools, dashboard assets, documentation, TOML rules, dependency notices, a CycloneDX 1.6 SBOM and per-file SHA-256 manifest. Python and LibreOffice are installed separately; no Office runtime or private workbook is distributed. The owned formatting/button demonstration is bundled with both launchers.

```powershell
cargo build --locked --release
python scripts/package.py --binary target/release/cellwright.exe --platform windows-x86_64 --out dist
```

```sh
cargo build --locked --release
python3 scripts/package.py --binary target/release/cellwright --platform linux-x86_64 --out dist
```

The packaging script uses sorted entries, fixed ZIP timestamps and executable Unix permissions. It refuses to overwrite archives and writes a `.zip.sha256` file. The SBOM covers the lockfile dependency graph, including build/dev dependencies and all platforms; it does not claim those are all runtime imports. Optional packages are pinned in requirements.txt. Version and installation provenance for Python, LibreOffice and Excel belong in execution evidence for an actual deployment.

The local `calibration-corpus/` and source-bearing `reports/` are outside the packager's directory allowlist and stay excluded from Git and release archives. Do not bundle the GPL Finance Tracker or CosMoS workbooks, or their extracted VBA, in a release. The Macquarie course workbook is local testing only. This exclusion applies to all 30 third-party corpus files; the portable real-corpus summary contains project-owned measurements and metadata only.

The Windows MSVC target enables `/Brepro` in `.cargo/config.toml` to avoid timestamp/random debug identifiers. Rebuilding with this config requires relinking existing artifacts. The generated SBOM is validated against the [primary CycloneDX 1.6 schema](https://github.com/CycloneDX/specification/blob/master/schema/bom-1.6.schema.json).

For reproducibility use the same Rust toolchain, target triple, lockfile, linker and build environment. Keep Linux source and build artifacts in the Linux filesystem when using WSL. Build into two separate target directories, package to separate output directories and compare native binary and archive hashes. Absolute source paths, linker versions and host toolchains can affect results; fixed archive timestamps alone do not establish a reproducible binary. Local comparisons are recorded in validation.md, with their scope.

CI checks Windows/Linux formatting, clippy, native and Python tests, and creates downloadable full archives. The fuzz job uses nightly/libFuzzer and has a short budget; longer campaigns belong on dedicated hosts. The [latest implementation CI run](https://github.com/scottcampbelldata/Cellwright/actions/runs/38032453984) passed for commit `24dac22`; [validation](validation.md) records the current checks.

The v0.1.0 preview archives are **unsigned** and available on [GitHub releases](https://github.com/scottcampbelldata/Cellwright/releases/tag/v0.1.0). Production Authenticode signing and Linux detached signatures require the owner's signing credentials. [Source is public on GitHub](https://github.com/scottcampbelldata/Cellwright), and [private vulnerability reporting](../SECURITY.md) is enabled. publiccode/mirror metadata, the openCode.de mirror, governance remain owner decisions. Native-language review, representative estate pilots and measured effort calibration remain release gates. Simulated workbook checks exercise scenarios without establishing production effort estimates.

The public project page is a static Cloudflare Pages site at `https://cellwright.scottcampbell.io`. Pages uses this repository's `main` branch, no framework or build command, and `site` as the output directory. Workbook processing remains in the loopback-only local dashboard; the public page has no upload or execution endpoint.
