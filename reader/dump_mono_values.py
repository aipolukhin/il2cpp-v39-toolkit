#!/usr/bin/env python3
"""
dump_mono_values.py — Stage 3 of the IL2CPP v39 toolkit.

Read the *serialized field VALUES* of IL2CPP MonoBehaviours straight out of a
Unity scene/asset file, using the per-class TypeTree JSON produced by Stage 2
(the patched Unity-Type-Tree-Generator).

Why this exists: for an IL2CPP game, Unity strips the runtime TypeTree from the
serialized files. UnityPy can therefore read native types (Camera, Transform,
MeshRenderer, GameObject...) but *not* your MonoBehaviours — it has no field
layout for them. Stage 1+2 reconstruct that layout as JSON; this script feeds
the JSON back into UnityPy so every [SerializeField] value becomes readable.

    python dump_mono_values.py \
        --assets  path/to/level_or_assets_file \
        --tt-json path/to/<Assembly>.json \
        --classes PlayerController LevelManager AudioManager

Notes
-----
* --assets may be a single serialized file OR a directory. Point it at a
  directory that also contains the split globalgamemanagers.assets (reassembled)
  so m_Script PPtrs resolve to class names; otherwise pass --no-resolve-script
  and rely on --classes-by-index.
* TypeTreeHelper.read_typetree_c is force-disabled: the C reader segfaults on the
  generic-heavy trees v39 games emit (UniTask<T> etc.). The pure-Python reader is
  slower but correct.
* JSON node format (from Stage 2) is the standard flat level-list:
      {"m_Type": "...", "m_Name": "...", "m_MetaFlag": 0|16384, "m_Level": N}
  which UnityPy's TypeTreeNode.from_list() consumes directly.
"""
import argparse
import json
import sys

import UnityPy
from UnityPy.helpers import TypeTreeHelper
from UnityPy.helpers.TypeTreeNode import TypeTreeNode

# The C reader crashes on the generic types v39 metadata emits — force pure Python.
TypeTreeHelper.read_typetree_c = False


def load_typetrees(tt_json_path):
    """Return {short_class_name: TypeTreeNode(root)} from a Stage-2 JSON file."""
    with open(tt_json_path) as fh:
        raw = json.load(fh)
    roots = {}
    for fullname, node_list in raw.items():
        short = fullname.split(".")[-1]
        try:
            roots[short] = TypeTreeNode.from_list(node_list)
        except ValueError as exc:  # malformed / unsupported layout for this class
            print(f"[warn] {short}: from_list failed: {exc}", file=sys.stderr)
    return roots


def iter_monobehaviours(env, asset_name):
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        if asset_name and getattr(obj, "assets_file", None):
            if obj.assets_file.name != asset_name:
                continue
        yield obj


def class_of(obj, resolve_script):
    if not resolve_script:
        return None
    try:
        d = obj.read(check_read=False)
        return d.m_Script.read().m_ClassName
    except Exception:  # m_Script unresolvable in this file set
        return None


def main():
    ap = argparse.ArgumentParser(description="Dump IL2CPP MonoBehaviour field values via reconstructed TypeTree JSON.")
    ap.add_argument("--assets", required=True, help="serialized file or directory (UnityPy.load target)")
    ap.add_argument("--tt-json", required=True, help="Stage-2 <Assembly>.json")
    ap.add_argument("--classes", nargs="*", default=None, help="short class names to dump (default: all found)")
    ap.add_argument("--asset-name", default=None, help="only read MonoBehaviours from this sub-asset (e.g. a scene 'levelN')")
    ap.add_argument("--no-resolve-script", action="store_true", help="do not resolve m_Script->class (dump every MB with each matching tree)")
    ap.add_argument("--out", default=None, help="write JSON result here instead of stdout pretty-print")
    args = ap.parse_args()

    roots = load_typetrees(args.tt_json)
    if not roots:
        sys.exit("no usable type trees in " + args.tt_json)
    want = set(args.classes) if args.classes else None
    resolve = not args.no_resolve_script

    env = UnityPy.load(args.assets)
    results = {}
    for obj in iter_monobehaviours(env, args.asset_name):
        cls = class_of(obj, resolve)
        if resolve:
            if cls is None or cls not in roots:
                continue
            if want and cls not in want:
                continue
            candidates = [cls]
        else:
            # no script resolution: try every wanted tree, keep whichever reads clean
            candidates = list(want or roots.keys())

        for cand in candidates:
            root = roots.get(cand)
            if root is None:
                continue
            try:
                data = obj.read_typetree(root)
            except Exception as exc:
                if resolve:
                    print(f"[warn] {cand} @ path {obj.path_id}: {type(exc).__name__} {exc}", file=sys.stderr)
                continue
            key = f"{cand}#{obj.path_id}"
            results[key] = data
            break

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(results, fh, indent=2, default=str)
        print(f"wrote {len(results)} MonoBehaviour(s) -> {args.out}")
    else:
        for key, data in results.items():
            print(f"\n=== {key} ===")
            for field, value in data.items():
                if field in ("m_GameObject", "m_Enabled", "m_Script", "m_ObjectHideFlags", "m_Name"):
                    continue
                s = str(value)
                print(f"   {field} = {s if len(s) < 300 else s[:300] + '...'}")
        print(f"\ndumped {len(results)} MonoBehaviour(s)", flush=True)


if __name__ == "__main__":
    main()
