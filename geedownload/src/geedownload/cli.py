"""Command line interface: geedownload datasets | search | download."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .catalog import list_datasets
from .errors import GeeDownloadError
from .utils import set_verbose


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geedownload", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("datasets", help="list the built-in datasets")

    s = sub.add_parser("search", help="search an area by name and (optionally) save its shapefile")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--country", help="country codes, e.g. sy,iq")
    s.add_argument("--save", metavar="DIR", help="save the picked candidate as a shapefile in DIR")
    s.add_argument("--pick", type=int, default=0)

    d = sub.add_parser("download", help="download satellite data for an area")
    d.add_argument("area", help='place name, shapefile path, or "west,south,east,north"')
    d.add_argument("-d", "--dataset", default="sentinel2")
    d.add_argument("--start")
    d.add_argument("--end")
    d.add_argument("--cloud", type=float, default=20, help="max cloud %% (default 20)")
    d.add_argument("--bands", nargs="+", help="band or group names (default: dataset defaults)")
    d.add_argument("--reducer", choices=["median", "mean", "min", "max", "sum", "mode", "first", "mosaic"])
    d.add_argument("--scale", type=float, help="pixel size in metres (default: native)")
    d.add_argument("--crs", help="e.g. EPSG:32637 (default: local UTM)")
    d.add_argument("--out", default=".")
    d.add_argument("--project", help="Earth Engine / Google Cloud project id")
    d.add_argument("--pick", type=int, default=0, help="which search candidate to use")
    d.add_argument("--buffer", type=float, default=0, help="buffer the area by N metres")
    d.add_argument("--mask-clouds", action="store_true")
    d.add_argument("--apply-scale", action="store_true", help="convert to physical units")
    d.add_argument("--per-image", action="store_true", help="download each scene instead of a composite")
    d.add_argument("--max-images", type=int, default=10)
    d.add_argument("--no-clip", action="store_true")
    d.add_argument("--no-stack", action="store_true")
    d.add_argument("--zip", action="store_true")
    d.add_argument("--map", action="store_true", help="also render a preview map (JPG) next to the data")

    m = sub.add_parser("map", help="render a map (JPG) from a GeoTIFF, or an outline map of an area")
    m.add_argument("raster", help='GeoTIFF path, or "-" for an outline-only map of --area')
    m.add_argument("-o", "--out", default="map.jpg")
    m.add_argument("--area", help="place name / shapefile / bbox for the boundary overlay")
    m.add_argument("--country", help="country name for borders and the inset")
    m.add_argument("--bands", nargs="+", help="1 band = colour bar, 3 bands = RGB (names or numbers)")
    m.add_argument("--cmap", default="viridis")
    m.add_argument("--classes", choices=["worldcover", "dynamic_world"])
    m.add_argument("--title")
    m.add_argument("--extent", choices=["area", "country"], default="area")
    m.add_argument("--admin1", action="store_true", help="draw state / province borders")
    m.add_argument("--dpi", type=int, default=200)

    sub.add_parser("catalogue", help="print the function catalogue (Markdown)").add_argument(
        "-o", "--out", help="write to this file instead of printing")

    sv = sub.add_parser("serve", help="run the REST API (needs geedownload[api])")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)

    g = sub.add_parser("gui", help="run the REST API and open the web interface (ar / fa / en)")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--port", type=int, default=8000)
    g.add_argument("--lang", choices=["ar", "fa", "en"], default=None)
    g.add_argument("--no-browser", action="store_true")

    sub.add_parser("about", help="author and contact information")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    set_verbose()
    try:
        if args.cmd == "datasets":
            for ds in list_datasets():
                print(f"{ds.key:18s} {ds.scale or '?':>8} m  {ds.collection_id}  - {ds.title}")
        elif args.cmd == "search":
            from .aoi import aoi_from_place
            from .boundary import save_boundary
            from .geocode import search_area

            places = search_area(args.query, limit=args.limit, country_codes=args.country)
            for i, pl in enumerate(places):
                print(f"[{i}] {pl}   bbox={tuple(round(v, 4) for v in pl.bbox)}")
            if args.save:
                print("saved:", save_boundary(aoi_from_place(places[args.pick]), args.save))
        elif args.cmd == "download":
            from .pipeline import download_area

            res = download_area(
                args.area, args.dataset, args.start, args.end, out_dir=args.out, bands=args.bands,
                cloud_max=args.cloud, reducer=args.reducer, scale=args.scale, crs=args.crs,
                clip=not args.no_clip, mask_clouds=args.mask_clouds, apply_scale=args.apply_scale,
                per_image=args.per_image, max_images=args.max_images, stack=not args.no_stack,
                zip_output=args.zip, buffer_m=args.buffer, pick=args.pick, project=args.project)
            print("folder   :", res.folder)
            print("shapefile:", res.shapefile)
            print("stack    :", res.stack)
            if args.map and res.stack:
                from .maps import plot_map, preview_args

                print("map      :", plot_map(res.stack, res.folder / "preview.jpg", area=res.shapefile,
                                             title=res.info["area"], country=res.info.get("country"),
                                             **preview_args(res.info)))
        elif args.cmd == "map":
            from .maps import plot_area, plot_map

            bands = [int(b) if b.isdigit() else b for b in args.bands] if args.bands else None
            if args.raster == "-":
                if not args.area:
                    raise GeeDownloadError("--area is required for an outline map")
                print(plot_area(args.area, args.out, country=args.country, extent=args.extent, title=args.title,
                                admin1=args.admin1, dpi=args.dpi))
            else:
                print(plot_map(args.raster, args.out, area=args.area, bands=bands, cmap=args.cmap,
                               classes=args.classes, title=args.title, country=args.country, admin1=args.admin1,
                               dpi=args.dpi))
        elif args.cmd == "catalogue":
            from .reference import function_catalogue

            text = function_catalogue()
            if args.out:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(text, encoding="utf-8")
                print("written:", args.out)
            else:
                print(text)
        elif args.cmd == "serve":
            import uvicorn

            uvicorn.run("geedownload.api:app", host=args.host, port=args.port)
        elif args.cmd == "gui":
            import threading
            import webbrowser

            import uvicorn

            url = f"http://{args.host}:{args.port}/app" + (f"?lang={args.lang}" if args.lang else "")
            print("GUI:", url)
            if not args.no_browser:
                threading.Timer(1.5, webbrowser.open, args=(url,)).start()
            uvicorn.run("geedownload.api:app", host=args.host, port=args.port)
        elif args.cmd == "about":
            from . import about

            about()
    except GeeDownloadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
