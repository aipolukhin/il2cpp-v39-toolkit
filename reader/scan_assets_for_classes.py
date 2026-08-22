#!/usr/bin/env python3
"""
Stage-3 companion to dump_mono_values.py — locate which serialized asset (Addressable BUNDLE or
scene) holds a given MonoBehaviour class, and rip its field VALUES via the Stage-2 typetree.

dump_mono_values.py targets a single file/dir; this one SWEEPS many assets (a whole Addressable
`Data/` set of hash-named UnityFS files) to answer "which bundle has class X, and what are its
values". Needed because in IL2CPP games the UI/gameplay PREFABS are often NOT in the level scenes
— they sit in per-asset Addressable bundles, instantiated at runtime.

TWO THINGS THAT COST HOURS THE FIRST TIME (both handled here):
  1. m_Script -> class name resolves ONLY when the target asset is loaded TOGETHER with the file
     that holds the MonoScripts (usually globalgamemanagers.assets). If that file is split
     (globalgamemanagers.assets.split0..N) it must be reassembled first: `cat split* > ggm.assets`.
     Pass it as --resolver.
  2. Do NOT trust `gc.choose(SomeUIComponent)` for existence — it returns false negatives. The
     serialized component list is the source of truth. This tool reads that truth.

Usage:
  python scan_assets_for_classes.py \
      --dir game/Data \
      --resolver /tmp/ggm.assets \
      --tt-json out/typetree/Assembly-CSharp.json \
      --classes MyController FooWidget BarPanel \
      --out /tmp/rip
Matches class short-names namespace-agnostically (endswith). Writes an asset->classes map +
per-class value JSON (each instance tagged with its source file).
"""
import argparse, os, re, json, glob
import UnityPy


def load_typetree_index(tt_json):
    if not tt_json or not os.path.exists(tt_json):
        return {}
    tt = json.load(open(tt_json))
    idx = {}
    for full, nodes in tt.items():
        short = full.split(".")[-1].split("+")[-1]
        idx.setdefault(short, nodes)
    return idx


def classname(o):
    try:
        return o.read(check_read=False).m_Script.read().m_ClassName or ""
    except Exception:
        return ""


def read_values(o, nodes):
    try:
        return o.read_typetree(nodes) if nodes else o.read(check_read=False).__dict__
    except Exception as e:
        return {"__read_error__": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser(description="Sweep bundles/scenes for MonoBehaviour classes and rip values")
    ap.add_argument("--dir", required=True, help="dir of serialized assets (Addressable bundles / scenes)")
    ap.add_argument("--resolver", default=None, help="companion file loaded alongside each asset so m_Script "
                    "resolves (usually a reassembled globalgamemanagers.assets)")
    ap.add_argument("--tt-json", default=None, help="Stage-2 <Assembly>.json for reading user-MB field values")
    ap.add_argument("--classes", nargs="+", required=True, help="short class names (matched by endswith)")
    ap.add_argument("--out", default="/tmp/asset_scan", help="output dir")
    ap.add_argument("--glob", default="[0-9a-f]" * 32, help="basename glob for asset files (default: 32-hex hash)")
    a = ap.parse_args()

    nodes_by_short = load_typetree_index(a.tt_json)
    files = sorted(glob.glob(os.path.join(a.dir, a.glob)))
    if not files:  # fall back to every regular file in the dir
        files = [f for f in sorted(glob.glob(os.path.join(a.dir, "*"))) if os.path.isfile(f)]
    print(f"scanning {len(files)} assets for {a.classes} (resolver={'yes' if a.resolver else 'NONE'})", flush=True)

    bundle_map, values = {}, {c: [] for c in a.classes}
    for i, f in enumerate(files):
        if i % 100 == 0:
            print(f"  {i}/{len(files)}", flush=True)
        try:
            env = UnityPy.load(a.resolver, f) if a.resolver else UnityPy.load(f)
        except Exception:
            continue
        base = os.path.basename(f)
        for o in env.objects:
            if o.type.name != "MonoBehaviour":
                continue
            cn = classname(o)
            short = next((c for c in a.classes if cn == c or cn.endswith("." + c) or cn.endswith("+" + c)), None)
            if not short:
                continue
            bundle_map.setdefault(base, []).append(short)
            values[short].append({"source": base, "path_id": int(o.path_id), "class": cn,
                                  "values": read_values(o, nodes_by_short.get(short))})

    os.makedirs(a.out, exist_ok=True)
    json.dump(bundle_map, open(os.path.join(a.out, "asset_class_map.json"), "w"), indent=1)
    for c in a.classes:
        json.dump(values[c], open(os.path.join(a.out, f"{c}_values.json"), "w"), indent=1, default=str)
        srcs = sorted({v["source"] for v in values[c]})
        print(f"{c}: {len(values[c])} instance(s) in {srcs}")


if __name__ == "__main__":
    main()
