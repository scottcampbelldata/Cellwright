# Local builds and release preparation

Rust 1.99.0 and Cargo.lock pin the native build. Full archives include the native scanner, Python tools, dashboard assets, documentation, TOML rules, dependency notices, a CycloneDX 1.6 SBOM and per-file SHA-256 manifest. Python and LibreOffice are installed separately; no Office runtime or private workbook is distributed.

```powershell
cargo build --locked --release
python scripts/package.py --binary target/release/macroferry.exe --platform windows-x86_64 --out dist
```

```sh
cargo build --locked --release
python3 scripts/package.py --binary target/release/macroferry --platform linux-x86_64 --out dist
```

The packaging script uses sorted entries, fixed ZIP timestamps and executable Unix permissions. It refuses to overwrite archives and writes a `.zip.sha256` file. The SBOM covers the lockfile dependency graph, including build/dev dependencies and all platforms; it does not claim those are all runtime imports. Optional packages are pinned in requirements.txt. Version and installation provenance for Python, LibreOffice and Excel belong in execution evidence for an actual deployment.

The Windows MSVC target enables `/Brepro` in `.cargo/config.toml` to avoid timestamp/random debug identifiers. Rebuilding with this config requires relinking existing artifacts. The generated SBOM is validated against the [primary CycloneDX 1.6 schema](https://github.com/CycloneDX/specification/blob/master/schema/bom-1.6.schema.json).

For reproducibility use the same Rust toolchain, target triple, lockfile, linker and build environment. Keep Linux source and build artifacts in the Linux filesystem when using WSL. Build into two separate target directories, package to separate output directories and compare native binary and archive hashes. Absolute source paths, linker versions and host toolchains can affect results; fixed archive timestamps alone do not establish a reproducible binary. Local comparisons are recorded in validation.md, with their scope.

CI checks Windows/Linux formatting, clippy, native and Python tests, and creates downloadable full archives. The fuzz job uses nightly/libFuzzer and has a short budget; longer campaigns belong on dedicated hosts. CI is configured locally and has not run on a hosted repository yet.

The local archives are **unsigned**. Production Authenticode signing and Linux detached signatures require the owner's signing credentials. Public hosting, truthful publiccode.yml URLs, the openCode.de mirror, release publication, private disclosure contact and governance remain owner decisions. No accounts, repository publication or certificates are fabricated. Native-language review, representative estate pilots and effort calibration are release gates rather than passing fixture tests.
