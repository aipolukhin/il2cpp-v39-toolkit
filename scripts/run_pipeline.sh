#!/usr/bin/env bash
# End-to-end IL2CPP v39 pipeline: binary+metadata  ->  DummyDlls  ->  TypeTree JSON.
#
# Usage:
#   run_pipeline.sh <libil2cpp.so> <global-metadata.dat> <out_dir> [assembly_filter]
#
# Produces:
#   <out_dir>/DummyDll/              clean v39 DummyDlls              (Stage 1)
#   <out_dir>/fakegame/game_Data/    Mono-mode staging for the gen    (glue)
#   <out_dir>/typetree/*.json        per-assembly TypeTree JSON       (Stage 2)
#
# Then read values with Stage 3:
#   python reader/dump_mono_values.py --assets <scene> --tt-json <out_dir>/typetree/<Asm>.json --classes ...
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${1:?libil2cpp.so path}"
META="${2:?global-metadata.dat path}"
OUT="${3:?output dir}"
FILTER="${4:-}"

mkdir -p "$OUT"

# ---- Stage 1: mydump -> clean v39 DummyDlls -------------------------------
DUMPER_DLL="$ROOT/dumper/bin/Release/net6.0/mydump.dll"
if [ ! -f "$DUMPER_DLL" ]; then
    echo "[stage1] building dumper..."
    ( cd "$ROOT/dumper" && dotnet build -c Release mydump.csproj )
fi
echo "[stage1] dumping DummyDlls..."
dotnet "$DUMPER_DLL" "$BIN" "$META" "$OUT"
# mydump writes DummyDll/ under CWD-relative 'out'; normalize location
[ -d "$OUT/DummyDll" ] || { echo "stage1 produced no DummyDll/"; exit 1; }
echo "[stage1] $(ls "$OUT/DummyDll" | wc -l) DummyDlls"

# ---- glue: stage DummyDlls as a fake Mono game so the gen skips its IL2CPP path
FAKE="$OUT/fakegame"
MANAGED="$FAKE/game_Data/Managed"
mkdir -p "$MANAGED"
cp "$OUT/DummyDll"/*.dll "$MANAGED"/
: > "$FAKE/game.exe"   # presence of an .exe + populated Managed => backend detected as "Mono"

# ---- Stage 2: type-tree generator (Mono mode) -----------------------------
GEN_DLL="$ROOT/typetree-gen/upstream/UnityTypeTreeGeneratorCLI/bin/Release/net6.0/UnityTypeTreeGeneratorCLI.dll"
if [ ! -f "$GEN_DLL" ]; then
    echo "[stage2] generator not built — run typetree-gen/setup.sh first"; exit 1
fi
echo "[stage2] generating type trees${FILTER:+ (filter: $FILTER)}..."
TT_FILTER="$FILTER" dotnet "$GEN_DLL" -p "$FAKE" -o "$OUT/typetree" -v 6000.3.15
echo "[stage2] JSON in $OUT/typetree/"
ls "$OUT/typetree/" 2>/dev/null || true
echo "[done] now read values: reader/dump_mono_values.py"
