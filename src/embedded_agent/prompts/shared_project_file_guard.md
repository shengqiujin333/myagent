# Shared Project File Guard

Treat build-contract files as project infrastructure, similar to a Makefile.

Protected files include `.uvprojx`, `.uvoptx`, `.sct`, `.ioc`, `Makefile`, `CMakeLists.txt`, linker scripts, startup files, and generated IDE project metadata.

Rules:

1. Change protected files only when the current task truly requires project registration, linker layout, startup, or build configuration changes.
2. Before changing a protected file, create a backup that can be restored without guessing.
3. Prefer small, targeted edits. Do not switch compiler versions, toolchain families, target devices, packs, output paths, or source registrations unless the task and build evidence require it.
4. After changing a protected file, run the real configured build tool and inspect the real build log for the current build.
5. Historical build logs and old artifacts are evidence only; they do not prove the current project still builds.
6. If the build tool fails before producing a build log, suspect project-file or tool invocation damage first. Use the latest backup as the recovery point before making another smaller edit.
7. Do not delete existing source registrations or bypass the configured build target just to make compilation pass.
8. When a protected-file change fails, record the backup path, changed file, build command, exit code, and failure evidence.
