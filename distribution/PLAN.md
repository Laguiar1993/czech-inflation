# Smaller working download

User request: a substantially smaller ZIP that downloads reliably on the second computer. Preserve the working models and manual-input instructions; keep the full repository and history available separately.

Design: publish a prebuilt release asset instead of asking GitHub to generate a ZIP of every historical evaluation. Keep all model/source code, docs, normal data, portable runtime assets, current production outputs and every dependency observed during dashboard validation and exact numerical replay. Omit old bulk evaluation outputs, unrelated scratch work, and unused raw paper/R14 research downloads. Preserve every retained source file byte-for-byte. Generate an explicitly labelled subset SOURCE_TREE manifest for this ZIP; do not alter the main repository's full manifest or any frozen model/input/output.

Implementation:
1. Measure compressed sizes and trace dashboard/nowcast/path file reads using the real runtime.
2. Build a standard Windows-compatible ZIP, target below 130 MB, with the same open-dashboard.cmd launcher and setup/manual guide. Retain the existing three packed assets so portable restore/verify commands remain unchanged.
3. Extract to a fresh directory. Run portable verify --models, check all model source files are present, and verify the dashboard hash and every retained file. Smoke-test current input preparation and momentum preparation where needed.
4. Publish the checked ZIP as a GitHub release asset, add a direct link to README, verify its server checksum and unauthenticated download response. Keep a sub-megabyte page-only option clearly labelled.
