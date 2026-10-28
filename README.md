# speaker-claim-audit

Version 0.1.0. An offline static audit comparing documentation about local sound emission with Python source evidence. Audited source is parsed as an AST and never executed. No third-party runtime dependencies are required.

Install and run:

```sh
python3 -m pip install .
speaker-claim-audit /path/to/project
python3 -m speaker_claim_audit /path/to/project --json
python3 -m speaker_claim_audit /path/to/project --verbose --ignore 'vendor/*' --ignore 'docs/generated/*'
python3 -m speaker_claim_audit /path/to/project --fail-on MEDIUM
python3 -m speaker_claim_audit --version
```

The positional root must be a readable directory. Repeatable `--ignore` globs match paths relative to that root. Root README.md and Markdown files beneath any docs component are checked. Fenced blocks are excluded; inline code counts. Matching folds case, contractions, hyphens, whitespace, and wrapped paragraph lines. Denials are removed before positive templates are matched.

Production source excludes tests, fixtures, docs, examples, test filename patterns, and symlinks. Imports and aliases resolve within each module. Supported providers are playsound, playsound2, pygame, sounddevice, simpleaudio, winsound, pydub.playback and pyaudio. Object routes require construction plus a driving call; pyaudio requires an explicit true output keyword. Verbose output lists source paths, lines and provider routes. JSON includes verdict, findings, evidence, test evidence and matched family flags.

A contradicted promise produces HIGH when production evidence is absent, or MEDIUM when evidence exists solely in tests. A contradicted denial produces HIGH when production evidence exists. Each family produces at most one finding. Without a matching template the result is PASS. Missing source contradicts a promise but is consistent with a denial.

Default failure threshold is HIGH. MEDIUM is reported with exit 0 unless `--fail-on MEDIUM` is selected. Exit 2 indicates failure at the selected threshold; exit 1 indicates invalid usage or an inaccessible root. `--version` prints 0.1.0.

## Limitations

Only the fixed documentation templates encoded in `speaker_claim_audit/phrases.py` are recognized. A bare device noun, user setup instructions, speech synthesis promises, file export promises, capture, screenshots and network sends are outside this audit's scope. The templates are deliberately exact; paraphrases may be missed.

External player helpers launched through subprocesses are outside the recognized routes. Shell command strings do not establish evidence. Imports, metadata reads, object construction alone, file writes, volume adjustments, capture and speech synthesis alone do not establish evidence either.

This is a static fingerprint check, not a hardware test. It cannot prove reachability, device availability or successful execution. Bindings are module-local and do not follow cross-module objects, dynamic imports or runtime reassignment. Invalid source is skipped. Symlinked source is skipped. Environment files are never read.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

The source distribution includes the test suite and fixtures. MIT licensed.
