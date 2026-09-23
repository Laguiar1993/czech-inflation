# Full-project private GitHub migration

Goal: transfer all tracked research code, models, input snapshots, results and the exact R35 dashboard to a private repository, with a reproducible Windows environment, Bloomberg pull commands and specific manual-input instructions.

Authorization: the user explicitly requested everything, including models, for another Bloomberg computer. Use the authenticated personal account Laguiar1993 and private repository czech-inflation. Preserve all frozen files and their bytes; add portable setup alongside them. No public hosting.

Architecture: preserve the complete tracked project and its history where GitHub size limits permit. Add a portable directory with setup, diagnostics, serving and current workflow commands. Keep dated research records immutable; fresh data and runs use new directories. The existing dashboard remains an immediately usable self-contained HTML snapshot. Runtime libraries and Bloomberg/X-13 installations are configured on the receiving computer rather than copied from user-specific environment folders.

Tasks:
- Inventory tracked and required untracked assets, history sizes, secrets and external runtime dependencies before any upload.
- Write portable/MANUAL_INPUTS.md with official links, exact schema/units, destination, frequency, release clocks, examples and validation for every non-Bloomberg input.
- Supply a pinned, tested Windows environment and explicit Bloomberg/X-13 installation and diagnostic checks.
- Add a project-relative launcher for serving R35, verifying the archive, capturing Bloomberg and preparing/running new forecast inputs using existing approved entry points. Avoid silent source substitution or fresh runs at historical clocks.
- Exercise a fresh checkout under a different path; verify forecast records, offline calculations and exact dashboard bytes. Record which live functions were actually tested and which require the destination terminal.
- Commit additive files, create the private repository, push the reviewed project, verify visibility/remote commit and a fresh clone. Include portable/START_HERE.md as the receiving-computer entry point.

Acceptance: the other computer can clone the full project, open the same dashboard, install a documented environment, identify and pull the required Bloomberg series, follow every manual-input instruction, and run the supported production commands with explicit checks. Any boundary for future source revisions or dates is documented rather than silently bypassed.
