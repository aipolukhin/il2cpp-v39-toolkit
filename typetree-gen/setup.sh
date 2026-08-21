#!/usr/bin/env bash
# Fetch AhmedAhmedEG/Unity-Type-Tree-Generator (MIT) and overlay our patched CLI.cs.
#
# We do NOT vendor the upstream's bundled Cpp2IL / LibCpp2IL / AssetsTools.NET
# binaries (Libs/*.dll) — cloning keeps their licensing and provenance intact.
# Our only change is CLI.cs (see CLI.cs.patched and ../docs/PIPELINE.md):
#   * TT_FILTER env var to restrict output to one assembly (huge speedup)
#   * per-assembly try/catch so one bad type can't abort the whole run
#   * 512 MB worker stack to survive Mono.Cecil's deep recursive ClearFullName
#
# The generator's *own* IL2CPP path can't parse metadata v39 — that's the whole
# reason Stage 1 (dumper/) exists. We run the generator in MONO mode instead:
# feed it the clean DummyDlls from Stage 1 in a fake <game>_Data/Managed folder.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HERE/upstream}"

if [ ! -d "$DEST/.git" ]; then
    git clone --depth 1 https://github.com/AhmedAhmedEG/Unity-Type-Tree-Generator "$DEST"
fi

cp "$HERE/CLI.cs.patched" "$DEST/UnityTypeTreeGeneratorCLI/CLI.cs"
echo "[setup] patched CLI.cs installed into $DEST"

( cd "$DEST" && dotnet build -c Release UnityTypeTreeGenerator.sln )
echo "[setup] built. CLI dll at: $DEST/UnityTypeTreeGeneratorCLI/bin/Release/net6.0/UnityTypeTreeGeneratorCLI.dll"
