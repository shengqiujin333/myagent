# Plan

Every task is directly completable and must not be split again.

## integrate-smoke-check

- Objective: Add a complete firmware smoke check module wired into main.
- Files: src/main.c
- Acceptance: build, CMSIS-DAP flash, serial contains `SMOKE OK`.
