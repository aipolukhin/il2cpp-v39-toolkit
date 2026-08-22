# IL2CPP v39 Toolkit

Read the **serialized field values of IL2CPP MonoBehaviours** out of a Unity 6
game — including games whose `global-metadata.dat` is **format version 39**,
which the mainstream tooling (Il2CppDumper, Cpp2IL/LibCpp2IL, AssetRipper's
bundled dumpers) does **not** parse.

Given an app's `libil2cpp.so` + `global-metadata.dat` and one of its scene/asset
files, this toolkit recovers concrete values like:

```
=== PlayerController#... ===
   targetCamera = {'m_FileID': 0, 'm_PathID': 42}
   uiRoot       = {'m_FileID': 0, 'm_PathID': 57}
   moveSpeed    = 6.5
   tintColor    = {'r': 0.2, 'g': 0.55, 'b': 0.9, 'a': 1.0}
```

i.e. the exact `[SerializeField]` wiring and inspector values of a stripped
IL2CPP build, read **statically** — no device, no Frida, no running the game.

> `v39` is the **format version of `global-metadata.dat`**, emitted by the
> Unity 6000.3.x line. It is *not* the Unity version. Confusing the two is why
> every off-the-shelf tool says "unsupported metadata version 39, we support
> 24–29".

---

## Why it takes three stages

For an **IL2CPP** build, Unity strips the runtime **TypeTree** from serialized
files. UnityPy (and every other asset reader) can then read Unity's *native*
types — `GameObject`, `Transform`, `Camera`, `MeshRenderer` — because their
layout is hard-coded, but it **cannot** read your `MonoBehaviour`s: there is no
field layout to deserialize against.

The layout lives in the C# metadata. So we reconstruct it:

| Stage | Tool | In | Out |
|------:|------|----|-----|
| **1** | `dumper/` (`mydump`) | `libil2cpp.so` + `global-metadata.dat` (**v39**) | clean **DummyDll**s (C# assemblies with the real field layouts) |
| **2** | `typetree-gen/` | DummyDlls | per-assembly **TypeTree JSON** |
| **3** | `reader/dump_mono_values.py` | TypeTree JSON + **one** scene/asset file | **field values** of every MonoBehaviour |
| **3′** | `reader/scan_assets_for_classes.py` | TypeTree JSON + a **directory** of bundles | which bundle holds class X + its values |

Stage 3 feeds the reconstructed TypeTree back into UnityPy so the MonoBehaviours
become as readable as the native types. Stage 3′ **sweeps** a whole Addressable set —
because in IL2CPP games the UI/gameplay **prefabs live in per-asset bundles, not the level
scenes**. It matches classes namespace-agnostically and rips each hit's values:

```bash
# reassemble the split MonoScript store first (else m_Script reads as "")
cat game/globalgamemanagers.assets.split* > /tmp/ggm.assets
python reader/scan_assets_for_classes.py --dir game/Data --resolver /tmp/ggm.assets \
   --tt-json out/typetree/Assembly-CSharp.json --classes MyController FooWidget
```

Two rip gotchas it handles: (1) `m_Script`→name resolves only when the asset is loaded
**together with** `globalgamemanagers` (reassemble its split parts, pass as `--resolver`);
(2) Addressable bundle magic bytes look like zeros but UnityPy still loads them.

---

## Quick start

Prereqs: **.NET 6 SDK** (`dotnet`), **Python 3.9+**.

```bash
# 0. deps
python -m venv .venv && . .venv/bin/activate
pip install -r reader/requirements.txt

# 1. build the v39 dumper (Stage 1)
dotnet build -c Release dumper/mydump.csproj

# 2. fetch + patch + build the type-tree generator (Stage 2)
bash typetree-gen/setup.sh

# 3. run stages 1+2 end-to-end
bash scripts/run_pipeline.sh \
    /path/to/libil2cpp.so \
    /path/to/global-metadata.dat \
    ./out \
    MyGame.Assembly          # optional: only this assembly (much faster)

# 4. read the values (Stage 3)
python reader/dump_mono_values.py \
    --assets   /path/to/level_or_scene \
    --tt-json  ./out/typetree/MyGame.Assembly.json \
    --classes  PlayerController LevelManager AudioManager
```

`--assets` may be a single serialized file or a directory. To resolve
`m_Script` → class names, point it at a directory that **also** contains the
game's `globalgamemanagers.assets` (reassembled if the platform split it);
otherwise pass `--no-resolve-script`.

---

## What each stage actually does

### Stage 1 — `dumper/` (mydump)

A **headless console** built from the parser classes of
[AndnixSH/Il2CppDumper-GUI](https://github.com/AndnixSH/Il2CppDumper-GUI) (a fork
of Perfare's Il2CppDumper that added metadata **v39** support). The GUI is
WinForms-only; `mydump` strips the UI and drives the parser directly:

```
Metadata(stream)                       # parse v39 header + tables
 -> Elf64(stream)                       # parse the ARM64 shared object
 -> SetProperties(version, usages)
 -> CheckDump / PlusSearch / Search / SymbolSearch   # locate Code+Metadata registration
 -> Il2CppExecutor
 -> DummyAssemblyExporter.Export        # emit DummyDll/*.dll
```

On a stripped binary (no symbols) `PlusSearch` — a section/segment-scoped,
count-validated pointer scan — finds the registration where the fast symbol
path can't. Output: `out/DummyDll/*.dll`, real assemblies whose types carry the
true serialized-field layout.

### Stage 2 — `typetree-gen/`

[AhmedAhmedEG/Unity-Type-Tree-Generator](https://github.com/AhmedAhmedEG/Unity-Type-Tree-Generator)
wraps AssetsTools.NET to turn assemblies into TypeTree JSON. Its **own** IL2CPP
path uses LibCpp2IL, which also chokes on v39 — so we **bypass it**: we stage
the Stage-1 DummyDlls as a fake **Mono** game (an `.exe` + a populated
`Managed/` folder), which makes the generator take its Mono branch and read the
DLLs with Mono.Cecil instead of trying to parse the v39 binary itself.

Our patch to `CLI.cs` (see `typetree-gen/CLI.cs.patched`) adds three things:

* `TT_FILTER` env var — restrict generation to one assembly (large games have
  hundreds; filtering is the difference between seconds and many minutes);
* per-assembly `try/catch` — one unsupported type no longer aborts the whole run;
* a **512 MB worker-thread stack** — Il2CppDumper DummyDlls have deep
  `DeclaringType` chains that overflow Mono.Cecil's recursive `ClearFullName`
  on the default 1 MB stack.

### Stage 3 — `reader/dump_mono_values.py`

Loads the scene with UnityPy, builds a `TypeTreeNode` root from the Stage-2 JSON
(`TypeTreeNode.from_list`), and calls `obj.read_typetree(root)` on each
MonoBehaviour to yield its field values.

`TypeTreeHelper.read_typetree_c` is force-disabled: the native C reader
segfaults on the generic-heavy trees v39 games emit (`UniTask<T>` and friends).
The pure-Python reader is slower but correct.

---

## The five walls this toolkit gets past

Every one of these is a dead end you hit trying to do this with stock tools:

1. **UnityPy native TypeTreeGenerator segfaults** on generic types → use
   reconstructed JSON + `read_typetree_c = False`.
2. **LibCpp2IL / Cpp2IL**: *"metadata version 39, we support 24–29"* → Stage-1
   dumper handles v39; generator runs in Mono mode off its output.
3. **Cpp2IL 2022.1 pre-release** parses v39 but then *"failed to find
   pCodegenModules"* (Unity 6 registration layout) → avoided entirely.
4. **Mono.Cecil `StackOverflowException`** on deep DummyDll type chains → 512 MB
   worker stack.
5. **Broken/corrupt DummyDlls** from half-working dumpers (circular
   `DeclaringType`) → the AndnixSH v39 parser emits clean assemblies.

---

## Layout

```
dumper/           Stage 1: headless v39 DummyDll generator (vendored, MIT)
typetree-gen/     Stage 2: CLI.cs patch + setup.sh (fetches upstream, MIT)
reader/           Stage 3: dump_mono_values.py + requirements.txt
scripts/          run_pipeline.sh — stages 1+2 end-to-end
docs/PIPELINE.md  deep dive, gotchas, the Mono-mode trick in detail
THIRD_PARTY.md    upstream projects + licenses
```

## Scope / legal

For interoperability and analysis of software **you are authorized to inspect**
(your own builds, security research, RE engagements with permission). Respect
the licenses and terms of the software you point it at. Vendored/fetched
upstreams are MIT; see `THIRD_PARTY.md`.

## Credits

Stands entirely on:
[Il2CppDumper](https://github.com/Perfare/Il2CppDumper) (Perfare) ·
[Il2CppDumper-GUI](https://github.com/AndnixSH/Il2CppDumper-GUI) (AndnixSH, v39) ·
[Unity-Type-Tree-Generator](https://github.com/AhmedAhmedEG/Unity-Type-Tree-Generator) (AhmedAhmedEG) ·
[UnityPy](https://github.com/K0lb3/UnityPy) (K0lb3) ·
[AssetsTools.NET](https://github.com/nesrak1/AssetsTools.NET) (nesrak1).
This toolkit is the glue + the v39 path between them.
