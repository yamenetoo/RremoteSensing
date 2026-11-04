"""Command line interface: ``splib07 download | list-remote | build | info | search | features | functions``."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .download import ITEM_ID, download_splib07, list_remote_files
from .library import SpectralLibrary, build_library


def _progress():
    try:
        from tqdm import tqdm
    except ImportError:
        return None, None
    bar = {"b": None}

    def cb(done, total):
        if bar["b"] is None:
            bar["b"] = tqdm(total=total, unit="B", unit_scale=True)
        bar["b"].n = done
        bar["b"].refresh()

    return cb, bar


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="splib07", description="USGS Spectral Library v7 tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list-remote", help="list files available on ScienceBase")
    s.add_argument("--item-id", default=ITEM_ID)

    s = sub.add_parser("download", help="download and extract the library")
    s.add_argument("dest")
    s.add_argument("--pattern", default="ASCIIdata_splib07b", help="regex for the zip name (default: oversampled ASCII data)")
    s.add_argument("--full", action="store_true", help="download the full usgs_splib07.zip (~5 GB)")
    s.add_argument("--no-extract", action="store_true")

    s = sub.add_parser("build", help="build a SpectralLibrary (.npz) from extracted data")
    s.add_argument("root")
    s.add_argument("out")
    s.add_argument("--library", default="splib07b")
    s.add_argument("--chapters", default=None, help="letters, e.g. MSV")
    s.add_argument("--kinds", default="AREF", help="comma separated, or 'all'")
    s.add_argument("--start", type=float, default=350)
    s.add_argument("--stop", type=float, default=2500)
    s.add_argument("--step", type=float, default=5)

    s = sub.add_parser("info", help="summarise a saved library")
    s.add_argument("lib")

    s = sub.add_parser("features", help="export sensor-band features to CSV")
    s.add_argument("lib")
    s.add_argument("out")
    s.add_argument("--sensor", default="sentinel2a")
    s.add_argument("--normalize", default=None, choices=["l2", "max", "minmax", "area"])
    s.add_argument("--continuum", action="store_true")

    s = sub.add_parser("search", help="find spectra by name in a saved library")
    s.add_argument("lib")
    s.add_argument("text")

    s = sub.add_parser("functions", help="print the catalogue of public functions")
    s.add_argument("--group", default=None)
    s.add_argument("--markdown", action="store_true", help="markdown (this is what docs/FUNCTIONS.md contains)")

    a = p.parse_args(argv)

    if a.cmd == "list-remote":
        for f in list_remote_files(a.item_id):
            print(f)
    elif a.cmd == "download":
        cb, _ = _progress()
        pattern = r"usgs_splib07" if a.full else a.pattern
        out = download_splib07(a.dest, pattern=pattern, extract=not a.no_extract, progress=cb)
        print(f"\nReady: {out}")
    elif a.cmd == "build":
        chapters = list(a.chapters) if a.chapters else None
        kinds = None if a.kinds.lower() == "all" else a.kinds.split(",")
        lib = build_library(a.root, a.library, chapters, kinds, start=a.start, stop=a.stop, step=a.step)
        print(lib.save(a.out), lib)
    elif a.cmd == "info":
        lib = SpectralLibrary.load(a.lib)
        print(lib)
        print(lib.meta.groupby(["chapter_name", "family"]).size().to_string())
    elif a.cmd == "features":
        lib = SpectralLibrary.load(a.lib)
        steps = (["continuum_removed"] if a.continuum else []) + [("to_sensor", {"sensor": a.sensor})]
        if a.normalize:
            steps.append(("normalized", {"method": a.normalize}))
        df = lib.pipeline(steps).to_frame()
        df.to_csv(a.out, index=False)
        print(f"Wrote {len(df)} rows x {df.shape[1]} columns to {a.out}")
    elif a.cmd == "search":
        print(SpectralLibrary.load(a.lib).search(a.text)[["name", "material", "chapter_name"]].to_string())
    elif a.cmd == "functions":
        from .functions import catalogue_markdown, list_functions

        if a.markdown:
            print(catalogue_markdown(), end="")
        else:
            print(list_functions(a.group)[["group", "name", "summary"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
