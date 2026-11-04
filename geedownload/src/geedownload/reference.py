"""Function catalogue: a generated reference of every public function, dataset, CLI command and REST endpoint.

`function_catalogue()` returns Markdown; docs/FUNCTION_CATALOGUE.md is produced by `geedownload catalogue -o ...`.
Signatures and descriptions are read from the code itself so the catalogue cannot drift out of date.
"""
from __future__ import annotations

import importlib
import inspect
import textwrap

SECTIONS = [
    ("1. Search an area and get its boundary", [
        ("geocode", ["search_area", "Place"]),
        ("aoi", ["resolve_aoi", "AOI", "aoi_from_place", "aoi_from_file", "buffer_aoi"]),
        ("maps", ["country_aoi"]),
        ("boundary", ["save_boundary", "read_boundary", "to_ee_geometry"]),
    ]),
    ("2. Datasets", [
        ("catalog", ["list_datasets", "get_dataset", "register_dataset", "Dataset", "with_overrides"]),
    ]),
    ("3. Download satellite data", [
        ("auth", ["init_ee"]),
        ("pipeline", ["download_area", "search_and_save", "DownloadResult"]),
    ]),
    ("4. Maps (cartopy, JPG)", [
        ("maps", ["plot_map", "plot_area", "preview_args"]),
    ]),
    ("5. Low-level Earth Engine helpers", [
        ("download", ["build_composite", "filter_collection", "apply_scale_factors", "resolve_bands", "detect_scale",
                      "download_band", "download_bands", "merge_tiles", "stack_bands"]),
        ("grid", ["utm_crs_for", "step_in_crs_units", "project_bbox", "snap_bounds", "grid_shape", "make_tiles",
                  "crs_transform"]),
    ]),
    ("6. Utilities", [
        ("utils", ["set_verbose", "slugify", "zip_dir"]),
        ("reference", ["function_catalogue"]),
        ("__init__", ["about"]),
    ]),
]

EXAMPLES = {
    "search_area": 'places = gd.search_area("Masyaf, Syria")\nfor i, p in enumerate(places): print(i, p)',
    "resolve_aoi": 'aoi = gd.resolve_aoi("Masyaf, Syria")\naoi = gd.resolve_aoi([42.35, 33.84, 42.55, 33.96])\naoi = gd.resolve_aoi("my_area.shp")',
    "country_aoi": 'syria = gd.country_aoi("Syria")\nhama = gd.country_aoi("Syria", admin1="Hama")',
    "save_boundary": 'shp = gd.save_boundary("Masyaf, Syria", out_dir="out")   # out/masyaf.shp (+ .shx .dbf .prj .cpg)',
    "read_boundary": 'geom = gd.read_boundary("out/masyaf.shp")   # shapely geometry, lon/lat',
    "list_datasets": 'for d in gd.list_datasets(): print(d.key, d.scale, d.collection_id)',
    "get_dataset": 'gd.get_dataset("s2")                       # alias\ngd.get_dataset("LANDSAT/LC08/C02/T1_L2")   # by asset id\ngd.get_dataset("MY/ASSET/ID")              # any Earth Engine asset',
    "register_dataset": 'gd.register_dataset(gd.Dataset("my_ds", "ORG/ASSET/ID", scale=30, default_bands=("b1", "b2")))',
    "init_ee": 'gd.init_ee("my-ee-project")',
    "download_area": ('res = gd.download_area("Masyaf, Syria", "sentinel2", "2023-06-01", "2023-09-30",\n'
                      '                       out_dir="out", cloud_max=10, bands=["B4", "B3", "B2", "B8"],\n'
                      '                       mask_clouds=True, project="my-ee-project")\n'
                      'print(res.shapefile, res.stack, res.metadata)'),
    "search_and_save": 'gd.search_and_save("Tabriz, Iran", out_dir="out")',
    "plot_map": ('gd.plot_map("out/.../masyaf_sentinel2_stack.tif", "masyaf_rgb.jpg", area="Masyaf, Syria",\n'
                 '            bands=["B4", "B3", "B2"], source="Sentinel-2 SR, summer 2023")   # RGB\n'
                 'gd.plot_map(stack, "ndvi.jpg", area="Masyaf, Syria", bands="NDVI", cmap="RdYlGn")        # colour bar\n'
                 'gd.plot_map(stack, "lc.jpg", area="Masyaf, Syria", classes="worldcover")                 # class legend'),
    "plot_area": 'gd.plot_area("Masyaf, Syria", "where.jpg")                    # zoom to the area, country inset\ngd.plot_area("Syria", "syria.jpg", extent="country", admin1=True)',
    "set_verbose": 'gd.set_verbose()   # print progress while downloading',
    "function_catalogue": 'print(gd.function_catalogue())',
    "about": 'gd.about()',
}


def _fmt_signature(name: str, obj) -> str:
    if inspect.isclass(obj):
        sig = inspect.signature(obj)
    else:
        sig = inspect.signature(obj)
    params = list(sig.parameters.values())
    if not params:
        return f"{name}()"
    lines = []
    for p in params:
        txt = p.name if p.kind is not p.VAR_KEYWORD else f"**{p.name}"
        if p.kind is p.VAR_POSITIONAL:
            txt = f"*{p.name}"
        if p.annotation is not inspect.Parameter.empty:
            txt += f": {p.annotation if isinstance(p.annotation, str) else getattr(p.annotation, '__name__', p.annotation)}"
        if p.default is not inspect.Parameter.empty:
            txt += f" = {p.default!r}"
        lines.append(txt)
    one = f"{name}({', '.join(lines)})"
    if len(one) <= 100:
        return one
    return f"{name}(\n" + "".join(f"    {l},\n" for l in lines) + ")"


def _doc(obj) -> str:
    return textwrap.dedent(inspect.getdoc(obj) or "(no description)").strip()


def _datasets_table() -> str:
    from .catalog import DATASETS, list_datasets

    alias = {}
    for k, ds in DATASETS.items():
        if k != ds.key:
            alias.setdefault(ds.key, []).append(k)
    rows = ["| key | aliases | Earth Engine id | scale (m) | cloud filter | default bands |", "|---|---|---|---|---|---|"]
    for d in list_datasets():
        rows.append(f"| `{d.key}` | {', '.join(f'`{a}`' for a in alias.get(d.key, [])) or '-'} | `{d.collection_id}` | "
                    f"{d.scale or 'auto'} | {d.cloud_property or '-'} | "
                    f"{', '.join(d.default_bands) if d.default_bands else 'all'} |")
    return "\n".join(rows)


def _cli_section() -> str:
    from .cli import _build_parser

    parser = _build_parser()
    out = []
    for action in parser._subparsers._group_actions[0].choices.items():
        name, sub = action
        out.append(f"### `geedownload {name}`\n\n```text\n{sub.format_help().strip()}\n```\n")
    return "\n".join(out)


def _api_section() -> str:
    try:
        from .api import app
    except ImportError:
        return "_Install `geedownload[api]` to list the REST endpoints._\n"
    rows = ["| method | path | description |", "|---|---|---|"]
    for r in app.routes:
        methods = getattr(r, "methods", None)
        if not methods or r.path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            continue
        for m in sorted(methods - {"HEAD", "OPTIONS"}):
            rows.append(f"| {m} | `{r.path}` | {getattr(r, 'summary', None) or r.name} |")
    return "\n".join(rows) + "\n"


def function_catalogue() -> str:
    """Markdown reference of all public functions (signature, description, example), datasets, CLI and REST API."""
    from . import AUTHOR, __version__

    out = [f"# geedownload {__version__} - function catalogue\n",
           f"Author: **{AUTHOR['name']}** - {AUTHOR['affiliation']} - {AUTHOR['email']}\n",
           "_Generated by `geedownload catalogue`; every example assumes `import geedownload as gd`._\n"]
    for title, modules in SECTIONS:
        out.append(f"\n## {title}\n")
        for mod_name, names in modules:
            mod = importlib.import_module("geedownload" if mod_name == "__init__" else f"geedownload.{mod_name}")
            for n in names:
                obj = getattr(mod, n)
                kind = "class" if inspect.isclass(obj) else "function"
                where = "geedownload" if mod_name == "__init__" else f"geedownload.{mod_name}"
                out.append(f"### `{n}`  \n_{kind} in `{where}`_\n")
                out.append("```python\n" + _fmt_signature(n, obj) + "\n```\n")
                out.append(_doc(obj) + "\n")
                if n in EXAMPLES:
                    out.append("**Example**\n\n```python\n" + EXAMPLES[n] + "\n```\n")
    out.append("\n## 7. Built-in datasets\n\n" + _datasets_table() + "\n")
    out.append("\n## 8. Command line\n\n" + _cli_section())
    out.append("\n## 9. REST API\n\nInteractive docs at `/docs` when the server runs.\n\n" + _api_section())
    return "\n".join(out).rstrip() + "\n"
