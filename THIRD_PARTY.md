# Third-party components

This toolkit is glue around several excellent open-source projects. All are MIT
licensed. Full upstream license texts are preserved next to the code that uses
them (`dumper/LICENSE-Il2CppDumper`, `typetree-gen/LICENSE-UnityTypeTreeGenerator`).

| Component | Upstream | License | How it's used here |
|-----------|----------|---------|--------------------|
| Il2CppDumper | [Perfare/Il2CppDumper](https://github.com/Perfare/Il2CppDumper) | MIT | Original IL2CPP metadata/ELF parser + DummyDll exporter. |
| Il2CppDumper-GUI (v39 fork) | [AndnixSH/Il2CppDumper-GUI](https://github.com/AndnixSH/Il2CppDumper-GUI) | MIT | Adds metadata **v39** support. Its parser classes are **vendored** into `dumper/src/` (unchanged except two small headless patches, noted in `docs/PIPELINE.md`). |
| Unity-Type-Tree-Generator | [AhmedAhmedEG/Unity-Type-Tree-Generator](https://github.com/AhmedAhmedEG/Unity-Type-Tree-Generator) | MIT | AssetsTools.NET wrapper that emits TypeTree JSON. **Not vendored** — `typetree-gen/setup.sh` clones it and overlays our patched `CLI.cs`. |
| UnityPy | [K0lb3/UnityPy](https://github.com/K0lb3/UnityPy) | MIT | Stage-3 asset reader (`pip` dependency, `reader/requirements.txt`). |
| AssetsTools.NET | [nesrak1/AssetsTools.NET](https://github.com/nesrak1/AssetsTools.NET) | MIT | Used transitively by the type-tree generator. |

## What is original to this repo

* `dumper/Program.cs`, `dumper/mydump.csproj`, `dumper/Il2CppDummyDll.dll`
  loader path, and the two headless patches in `dumper/src`
  (`Utils/DummyAssemblyGenerator.cs`, `Config.cs`, `_GuiStubs.cs`).
* `typetree-gen/CLI.cs.patched` (the `TT_FILTER` / try-catch / 512 MB-stack
  patch) and `typetree-gen/setup.sh`.
* `reader/dump_mono_values.py`.
* `scripts/run_pipeline.sh` and all of `docs/`.

These original parts are MIT licensed — see `LICENSE`.

## Vendored source note

`dumper/src/` contains source files from Il2CppDumper / Il2CppDumper-GUI (MIT).
They are redistributed here under the terms of that license, with the copyright
notice preserved in `dumper/LICENSE-Il2CppDumper`. If you prefer not to
redistribute them, delete `dumper/src/` and re-fetch from the upstream fork,
then re-apply the two headless patches described in `docs/PIPELINE.md`.
