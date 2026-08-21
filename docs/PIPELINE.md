# Pipeline deep dive

This document explains the design decisions and the non-obvious tricks. Read the
top-level `README.md` first for the overview.

## The core problem, precisely

IL2CPP ahead-of-time compiles C# to native code. At build time Unity can strip
the **TypeTree** — the per-type field-layout table — from serialized files,
because the AOT runtime doesn't need it. Editor/native types (`GameObject`,
`Transform`, `Camera`, `Renderer`, …) still deserialize because their layouts
are compiled into every reader. **User `MonoBehaviour`s do not**: their layout
existed only in the stripped TypeTree.

To read a MonoBehaviour's fields you therefore need to *reconstruct* its
TypeTree. The field layout is recoverable from the C# metadata that IL2CPP
ships alongside the native code:

* `libil2cpp.so` (or `GameAssembly.dll` on desktop) — native code + registration
  tables that map metadata indices to runtime data.
* `global-metadata.dat` — the metadata blob: strings, type defs, field defs,
  method defs, etc. Its **format version** is what "v39" refers to.

## Why v39 breaks everything

The metadata format is versioned independently of Unity. Unity 6000.3.x emits
**version 39**. The reference implementations everyone's tooling is built on —
Perfare's Il2CppDumper and Sam's LibCpp2IL — top out around v29/v31. When they
hit a v39 header they either reject it outright ("we support 24–29") or misparse
the variable-width table indices and produce garbage / corrupt assemblies.

Two things changed enough to matter:

* header/table shape (new fields, wider indices in places);
* on Unity 6 the code-registration is found differently — Cpp2IL's newer builds
  parse the metadata but then fail to locate `pCodegenModules`.

## Stage 1: getting clean v39 DummyDlls

The one parser that keeps up with v39 is **AndnixSH's Il2CppDumper-GUI** fork —
its `Metadata.cs` accepts `version > 39`-style headers and handles the
variable-width table indices. But it's a WinForms app; there's no headless mode
and it won't build on Linux/CI.

`mydump` (in `dumper/`) is a ~30-line `Program.cs` plus the fork's parser
classes (`src/`, unchanged, MIT). It reproduces the GUI's dump path headlessly:

```csharp
var metadata = new Metadata(new MemoryStream(File.ReadAllBytes(meta)));
Il2Cpp il2Cpp = new Elf64(new MemoryStream(File.ReadAllBytes(so)));   // ARM64 .so
il2Cpp.SetProperties(metadata.Version, metadata.metadataUsagesCount);

bool ok = il2Cpp.CheckDump()
       || il2Cpp.PlusSearch(methodCount, typeCount, imageCount)       // <- the one that works on stripped .so
       || il2Cpp.Search()
       || il2Cpp.SymbolSearch();

var executor = new Il2CppExecutor(metadata, il2Cpp);
DummyAssemblyExporter.Export(executor, outDir, addToken: false);      // -> outDir/DummyDll/*.dll
```

### Registration search: naive vs optimized

`mydump` tries, in order:

* `CheckDump` — trivial: is this already a dumped-to-memory image?
* `PlusSearch` — the **optimized** search. It scans the ELF `PT_LOAD`
  segments (and named sections when present), looking for the
  `Il2CppCodeRegistration` / `Il2CppMetadataRegistration` structures, and
  **validates** each candidate by checking that the counts it points at
  (`methodPointersCount`, `typeDefinitionsCount`, `imagesCount`) match what the
  metadata says. Candidate pointers that don't validate are rejected — that's
  what makes it robust on a stripped binary with no symbol table.
* `Search` — a naive brute-force fallback.
* `SymbolSearch` — fastest, but needs an unstripped symbol table (rare on
  shipping mobile builds).

On the games this was built for, symbols are stripped, so `SymbolSearch` can't
run; `PlusSearch` succeeds via the segment scan. It's slower than a symbol
lookup but it's a bounded, validated scan — not an unbounded brute force.

Only the two small patches distinguish `dumper/src` from the upstream fork:

* `Utils/DummyAssemblyGenerator.cs` reads the embedded `Il2CppDummyDll.dll` from
  `AppContext.BaseDirectory` instead of a WPF `Resource1` (so it works outside
  the GUI). `Il2CppDummyDll.dll` is shipped next to the built binary.
* `Config.cs` / `_GuiStubs.cs` stub the GUI-only bits (`MainForm.Log`,
  `Brushes`, WPF config) so the parser links in a console app.

## Stage 2: the Mono-mode trick

The type-tree generator has two backends:

```csharp
if (Directory.Exists(Managed) && Managed has *.dll) unityBackend = "Mono";
else if (GameAssembly.dll && global-metadata.dat)   unityBackend = "IL2CPP";
```

Its **IL2CPP** branch calls `Cpp2IlApi.InitializeLibCpp2Il(...)` — which is
exactly the LibCpp2IL that can't do v39. Its **Mono** branch just reads the
`.dll`s in `Managed/` with Mono.Cecil.

So we lie to it. `scripts/run_pipeline.sh` builds a fake game directory:

```
out/fakegame/
  game.exe                     # empty file — just needs to exist
  game_Data/Managed/*.dll      # the CLEAN DummyDlls from Stage 1
```

`UnityGameAnalyzer` sees a populated `Managed/` → picks **Mono** → never touches
LibCpp2IL → reads our reconstructed assemblies directly. This is the crux of the
whole toolkit: **Stage 1 does the v39 parse once, and Stage 2 consumes the
result as if it were an ordinary Mono game.**

### The three CLI.cs patches (and why)

* **`TT_FILTER`** — `GenerateAssemblyTypeTree` is O(types) and large titles have
  500+ assemblies. Filtering to the one you care about (`TT_FILTER=MyGame.Core`)
  turns minutes into seconds.
* **per-assembly `try/catch`** in `DumpJson` — a single type the generator can't
  template (odd generic, unsupported base) used to throw and lose *all* output.
  Now it logs `SKIP <asm>` and keeps the rest.
* **512 MB worker stack** in `Main` — Il2CppDumper DummyDlls nest
  `DeclaringType` deeply; Mono.Cecil's `ClearFullName` recurses per level and
  overflows the default 1 MB thread stack. Running the whole job on a
  `new Thread(..., 512*1024*1024)` fixes the `StackOverflowException`.

## Stage 3: reading values back

```python
from UnityPy.helpers import TypeTreeHelper
TypeTreeHelper.read_typetree_c = False          # C reader segfaults on generics

root = TypeTreeNode.from_list(json_nodes)        # nodes: [{m_Type,m_Name,m_MetaFlag,m_Level}, ...]
data = mono_obj.read_typetree(root)              # -> dict of field -> value
```

Gotchas:

* **`read_typetree_c = False` is mandatory.** The native reader crashes on
  `UniTask<T>`-style generic fields. Setting `read_typetree=False` on the
  *reader* alone doesn't help — it's the generator that crashes; the toggle
  above is the one that matters.
* **JSON node shape** is the flat level-list Unity uses:
  `{"m_Type","m_Name","m_MetaFlag","m_Level"}`. `from_list` consumes it directly
  and raises `ValueError` if `m_Level`/`m_Type`/`m_Name` are missing.
* **`m_Script` resolution** needs the file that holds the script PPtr targets —
  usually `globalgamemanagers.assets`. On some platforms it's split into
  numbered parts; `cat` them back in numeric order and load the directory so
  UnityPy can resolve class names. Or skip it with `--no-resolve-script`.
* **PPtr values** come back as `{'m_FileID': f, 'm_PathID': p}`. Resolve `p`
  against the same scene's object list to get the referenced GameObject/asset
  name — that's how you turn `targetCamera = PathID 42` into "the Main Camera
  GameObject".
* **Occasional per-class read error** (`Expected to read N bytes, but only read
  M`) means the reconstructed layout for that one class is slightly off (usually
  an alignment/`m_MetaFlag` edge). The other classes still read fine; inspect
  that class's JSON nodes if you need it.

## Worked example

Against a Unity 6000.3.x IL2CPP ARM64 build, dumping one gameplay assembly:

```bash
bash scripts/run_pipeline.sh libil2cpp.so global-metadata.dat ./out MyGame.Gameplay
python reader/dump_mono_values.py --assets ./scene_dir \
  --tt-json ./out/typetree/MyGame.Gameplay.json \
  --classes PlayerController LevelManager AudioManager
```

`./scene_dir` = the scene file + the reassembled `globalgamemanagers.assets`
(numeric-ordered parts `cat`'d together) so `m_Script` resolves.
