# Security and privacy

The native scanner reads originals, never invokes Office or executes macros, never refreshes connections and makes no network requests. Reports embed resources. Each workbook is isolated in a timed process: default two workers, 128 MiB input, 16 MiB per part/stream, 256 MiB aggregate ZIP, 10,000 entries, CFB depth 32, XML depth 128/one million events and 64 MiB response. Reads/decompression are bounded; DTDs/encrypted ZIP entries are rejected. These controls are not an OS memory sandbox or malware-analysis certification.

VBA editor protection is metadata, not encryption. `--skip-protected` omits protected/unknown-protection VBA. Password-to-open encryption is detected without decryption. `--no-source` removes VBA/M/designer data from reports; CSV never contains source. Metadata includes paths, names, owner identifiers, hashes/references/findings. Dashboard scans default to source-free reports. Extraction/conversion outputs contain source and can be confidential.

HTML escapes workbook content and uses CSP. CSV neutralises formula cells. Generated filenames are sanitised; output directories must be new/empty. Designer snapshots have a 16 MiB aggregate bound. Cache/source flags are heuristics; p-code is not decompiled and signatures are not verified.

Conversion disables automatic macros/link updates, writes new files and preserves source/diffs. ODS candidates remove other imported Basic libraries and document/sheet event bindings. Additional control bindings require review. Unsupported Basic code remains intact with TODOs, so candidates can contain unsafe original routines.

Capture/verify/run-python require explicit execution consent for **trusted code**. Office/Python execution is not sandboxed and can access files, network and services. Use a disposable VM for untrusted code. The harness invokes the named routine, suppresses open events, uses private LibreOffice profiles, bounds runtime/cell captures, closes its own Office instances and checks the original hash. It cannot prevent external side effects. Passing cases cover only observed inputs/cells.

M execution is allowlisted, without arbitrary eval. File sources must resolve within `--data-root` and bounded size; network providers are unsupported. General M semantics/resource isolation are incomplete. openpyxl cannot calculate formulas.

The dashboard binds to loopback, validates Host/Origin, uses a random session token, HttpOnly same-site download cookie, CSP, parameterised SQLite, bounded JSON and resolved artifact paths. It has no remote/multi-user authentication. Do not expose the port publicly. Schedules run only with the server; use distinct data directories per instance. Filesystem users can read stored results.

Local binaries are unsigned; SBOM/hash manifests are not attestations. No independent security audit, broad estate campaign or production signing/publication has occurred. Until a real disclosure channel exists, contact the owner privately without posting confidential workbooks/source.
