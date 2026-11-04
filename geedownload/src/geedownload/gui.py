"""Desktop GUI (Tkinter) in Arabic, Persian and English.

Run with ``geedownload gui`` (or ``python -m geedownload.gui``). It calls the Python functions directly - no web server.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import AUTHOR, __version__

I18N = json.loads((Path(__file__).parent / "assets" / "gui" / "i18n.json").read_text(encoding="utf-8"))
LANG_NAMES = {"ar": "العربية", "fa": "فارسی", "en": "English"}
FEATURE_TYPES = ["", "country", "state", "city", "settlement"]
FT_KEYS = ["ft_any", "ft_country", "ft_state", "ft_city", "ft_settlement"]
REDUCERS = ["", "median", "mean", "min", "max", "sum", "mode", "first", "mosaic"]


def _shaper():
    """Arabic letter shaping + bidi for Tk builds that lack it (typically Tk on Linux)."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return None
    return lambda s: get_display(arabic_reshaper.reshape(s))


class QueueHandler(logging.Handler):
    def __init__(self, q):
        super().__init__()
        self.q = q

    def emit(self, record):
        self.q.put(("log", self.format(record)))


class App(tk.Tk):
    def __init__(self, lang: str = "en"):
        super().__init__()
        self.geometry("980x720")
        self.minsize(760, 560)
        self.lang = lang if lang in I18N else "en"
        self.shape = _shaper() if sys.platform.startswith("linux") else None
        self.bound: list = []          # (widget, key, option) for live translation
        self.q: queue.Queue = queue.Queue()
        self.places: list = []
        self.selected = None           # {"label", "place"}
        self.datasets = []
        self.busy = False
        self.images = []
        try:
            from .catalog import list_datasets
            self.datasets = list(list_datasets())
        except Exception:
            pass
        self._build()
        self.set_lang(self.lang)
        self.after(120, self._pump)
        from .utils import logger
        h = QueueHandler(self.q)
        h.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)

    # ---------------------------------------------------------------- i18n helpers
    def tr(self, key: str) -> str:
        text = I18N[self.lang].get(key) or I18N["en"].get(key, key)
        return self.shape(text) if (self.shape and self.lang in ("ar", "fa")) else text

    def _tab_text(self, key: str) -> str:
        text = I18N[self.lang][key].replace("4.", "3.", 1)      # the desktop GUI has no separate jobs tab
        return self.shape(text) if (self.shape and self.lang in ("ar", "fa")) else text

    def _lang_display(self, code: str) -> str:
        name = LANG_NAMES[code]
        return self.shape(name) if (self.shape and code in ("ar", "fa")) else name

    def bind_text(self, widget, key, option="text"):
        self.bound.append((widget, key, option))
        widget.configure(**{option: self.tr(key)})
        return widget

    def set_lang(self, lang: str):
        self.lang = lang
        rtl = lang in ("ar", "fa")
        for w, key, opt in self.bound:
            w.configure(**{opt: self.tr(key)})
        for lb in self.labels:
            lb.configure(anchor="e" if rtl else "w", justify="right" if rtl else "left")
        self.title(self.tr("gui_title") + " " + __version__)
        for i, k in enumerate(self.tab_keys):
            self.nb.tab(i, text=self._tab_text(k))
        self.ft_box.configure(values=[self.tr(k) for k in FT_KEYS])
        self.ft_box.current(0)
        self.ext_box.configure(values=[self.tr("extent_area"), self.tr("extent_country")])
        self.ext_box.current(0)
        self.red_box.configure(values=[self.tr("reducer_default")] + REDUCERS[1:])
        self.red_box.current(0)
        self._refresh_selected()
        self.lang_cb.configure(values=[self._lang_display(c) for c in LANG_NAMES])
        self.lang_var.set(self._lang_display(lang))
        if rtl and sys.platform.startswith("linux") and not self.shape:
            self.log_write(I18N["en"]["lang_note"])

    # ---------------------------------------------------------------- layout
    def _label(self, parent, key, **kw):
        lb = ttk.Label(parent, **kw)
        self.bind_text(lb, key)
        self.labels.append(lb)
        return lb

    def _build(self):
        self.labels: list = []
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="geedownload", font=("TkDefaultFont", 15, "bold")).pack(side="left")
        self.lang_var = tk.StringVar()
        self.lang_cb = ttk.Combobox(top, textvariable=self.lang_var, state="readonly", width=10)
        self.lang_cb.pack(side="right")
        self.lang_cb.bind("<<ComboboxSelected>>", lambda e: self.set_lang(list(LANG_NAMES)[self.lang_cb.current()]))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8)
        self.tab_keys = ["tab_search", "tab_download", "tab_maps", "tab_about"]
        self.t_search, self.t_dl, self.t_maps, self.t_about = (ttk.Frame(self.nb, padding=10) for _ in range(4))
        for f in (self.t_search, self.t_dl, self.t_maps, self.t_about):
            self.nb.add(f, text="")
        self._build_search()
        self._build_download()
        self._build_maps()
        self._build_about()

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status).pack(fill="x", padx=10)
        self.log = tk.Text(self, height=7, state="disabled", wrap="word")
        self.log.pack(fill="x", padx=8, pady=(0, 8))

    def _build_search(self):
        f = self.t_search
        f.columnconfigure(1, weight=1)
        self._label(f, "search_title", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="ew")
        self.q = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.q)
        e.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        e.bind("<Return>", lambda ev: self.do_search())
        self.btn_search = self.bind_text(ttk.Button(f, command=self.do_search), "search_btn")
        self.btn_search.grid(row=1, column=2, padx=4)
        self._label(f, "country_codes").grid(row=2, column=0, sticky="ew")
        self.cc = tk.StringVar()
        ttk.Entry(f, textvariable=self.cc, width=14).grid(row=2, column=1, sticky="w")
        self._label(f, "feature_type").grid(row=3, column=0, sticky="ew")
        self.ft_box = ttk.Combobox(f, state="readonly", width=20)
        self.ft_box.grid(row=3, column=1, sticky="w")
        self.tree = ttk.Treeview(f, columns=("name", "type", "poly", "disp"), show="headings", height=9)
        for c, w in (("name", 140), ("type", 90), ("poly", 70), ("disp", 520)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w)
        self.tree.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=6)
        f.rowconfigure(4, weight=1)
        bar = ttk.Frame(f)
        bar.grid(row=5, column=0, columnspan=3, sticky="ew")
        self.bind_text(ttk.Button(bar, command=self.use_area), "use_area").pack(side="left", padx=2)
        self.bind_text(ttk.Button(bar, command=self.save_shp), "save_shp").pack(side="left", padx=2)
        self.sel_label = ttk.Label(bar)
        self.sel_label.pack(side="left", padx=12)

    def _build_download(self):
        f = self.t_dl
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)
        self.v = {k: tk.StringVar() for k in ("bbox", "start", "end", "cloud", "bands", "scale", "crs", "buffer", "maxn", "out", "project")}
        self.v["cloud"].set("20"); self.v["buffer"].set("0"); self.v["maxn"].set("10")
        self.v["out"].set(str(Path.home() / "geedownload_out")); self.v["project"].set(os.environ.get("EE_PROJECT", ""))
        self.chk = {k: tk.BooleanVar(value=d) for k, d in (("mask", False), ("scale", False), ("clip", True), ("per", False), ("map", True))}
        r = 0
        self._label(f, "selected_area").grid(row=r, column=0, sticky="ew")
        self.dl_area = ttk.Label(f)
        self.dl_area.grid(row=r, column=1, sticky="w")
        self._label(f, "or_bbox").grid(row=r, column=2, sticky="ew")
        ttk.Entry(f, textvariable=self.v["bbox"]).grid(row=r, column=3, sticky="ew")
        self.ds_var = tk.StringVar()
        rows = [("dataset", None), ("start_date", "start"), ("end_date", "end"), ("cloud_max", "cloud"), ("bands", "bands"),
                ("reducer", None), ("scale", "scale"), ("crs", "crs"), ("buffer", "buffer"), ("max_images", "maxn"),
                ("ee_project", "project"), ("out_dir", "out")]
        for i, (key, var) in enumerate(rows):
            rr, cc = 1 + i // 2, (i % 2) * 2
            self._label(f, key).grid(row=rr, column=cc, sticky="ew", pady=2)
            if key == "dataset":
                cb = ttk.Combobox(f, textvariable=self.ds_var, state="readonly", values=[d.key for d in self.datasets])
                if self.datasets:
                    cb.current(0)
                cb.grid(row=rr, column=cc + 1, sticky="ew")
                self.ds_box = cb
            elif key == "reducer":
                self.red_box = ttk.Combobox(f, state="readonly")
                self.red_box.grid(row=rr, column=cc + 1, sticky="ew")
            elif key == "out_dir":
                box = ttk.Frame(f)
                box.grid(row=rr, column=cc + 1, sticky="ew")
                ttk.Entry(box, textvariable=self.v["out"]).pack(side="left", fill="x", expand=True)
                self.bind_text(ttk.Button(box, width=10, command=lambda: self._pick_dir(self.v["out"])), "browse").pack(side="left")
            else:
                ttk.Entry(f, textvariable=self.v[var]).grid(row=rr, column=cc + 1, sticky="ew")
        r = 8
        chk = ttk.Frame(f)
        chk.grid(row=r, column=0, columnspan=4, sticky="ew", pady=6)
        for key, name in (("opt_mask_clouds", "mask"), ("opt_apply_scale", "scale"), ("opt_clip", "clip"),
                          ("opt_per_image", "per"), ("opt_make_map", "map")):
            c = ttk.Checkbutton(chk, variable=self.chk[name])
            self.bind_text(c, key)
            c.pack(side="left", padx=6)
        self.btn_dl = self.bind_text(ttk.Button(f, command=self.do_download), "start_job")
        self.btn_dl.grid(row=r + 1, column=0, columnspan=4, pady=6)

    def _build_maps(self):
        f = self.t_maps
        f.columnconfigure(1, weight=1)
        self.m = {k: tk.StringVar() for k in ("raster", "bands", "title", "country", "dpi", "a_name", "a_country")}
        self.m["dpi"].set("150")
        self.m_cmap, self.m_classes, self.m_admin1 = tk.StringVar(value="viridis"), tk.StringVar(), tk.BooleanVar()
        self._label(f, "map_note").grid(row=0, column=0, columnspan=3, sticky="ew")
        self._label(f, "raster").grid(row=1, column=0, sticky="ew")
        ttk.Entry(f, textvariable=self.m["raster"]).grid(row=1, column=1, sticky="ew")
        self.bind_text(ttk.Button(f, command=self._pick_raster), "browse").grid(row=1, column=2)
        for i, (key, var) in enumerate((("map_bands", "bands"), ("map_title", "title"), ("map_country", "country"), ("map_dpi", "dpi"))):
            self._label(f, key).grid(row=2 + i, column=0, sticky="ew")
            ttk.Entry(f, textvariable=self.m[var]).grid(row=2 + i, column=1, sticky="ew")
        self._label(f, "map_cmap").grid(row=6, column=0, sticky="ew")
        ttk.Combobox(f, textvariable=self.m_cmap, values=["viridis", "RdYlGn", "gray", "terrain", "magma", "Blues"]).grid(row=6, column=1, sticky="w")
        self._label(f, "map_classes").grid(row=7, column=0, sticky="ew")
        ttk.Combobox(f, textvariable=self.m_classes, values=["", "worldcover", "dynamic_world"], state="readonly").grid(row=7, column=1, sticky="w")
        self.bind_text(ttk.Button(f, command=self.do_raster_map), "render_map").grid(row=8, column=0, columnspan=2, pady=6)
        ttk.Separator(f).grid(row=9, column=0, columnspan=3, sticky="ew", pady=6)
        self._label(f, "area_map_title", font=("TkDefaultFont", 11, "bold")).grid(row=10, column=0, columnspan=3, sticky="ew")
        self._label(f, "area_text").grid(row=11, column=0, sticky="ew")
        ttk.Entry(f, textvariable=self.m["a_name"]).grid(row=11, column=1, sticky="ew")
        self._label(f, "extent").grid(row=12, column=0, sticky="ew")
        self.ext_box = ttk.Combobox(f, state="readonly")
        self.ext_box.grid(row=12, column=1, sticky="w")
        self._label(f, "map_country").grid(row=13, column=0, sticky="ew")
        ttk.Entry(f, textvariable=self.m["a_country"]).grid(row=13, column=1, sticky="ew")
        self.bind_text(ttk.Checkbutton(f, variable=self.m_admin1), "opt_admin1").grid(row=14, column=1, sticky="w")
        self.bind_text(ttk.Button(f, command=self.do_area_map), "render_area_map").grid(row=15, column=0, columnspan=2, pady=6)

    def _build_about(self):
        f = self.t_about
        self._label(f, "about_text", wraplength=800).pack(fill="x", pady=4)
        ttk.Label(f, text=f"v{__version__}").pack(anchor="w")
        self.au_name = ttk.Label(f)
        self.au_name.pack(anchor="w", pady=2)
        ttk.Label(f, text=AUTHOR["affiliation"]).pack(anchor="w")
        ttk.Label(f, text=AUTHOR["email"]).pack(anchor="w")
        for name, url in (("GitHub", AUTHOR["github"]), ("Web", AUTHOR["website"]), ("Scholar", AUTHOR["scholar"]), ("ORCID", AUTHOR["orcid"])):
            ttk.Button(f, text=f"{name}: {url}", command=lambda u=url: webbrowser.open(u)).pack(anchor="w", pady=1)
        self.au_name.configure(text=f"{AUTHOR['name']} ({AUTHOR['arabic_name']})")

    # ---------------------------------------------------------------- utilities
    def log_write(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log_write(payload)
                elif kind == "call":
                    payload()
        except queue.Empty:
            pass
        self.after(120, self._pump)

    def run_bg(self, work, done, buttons=()):
        """Run ``work`` in a thread; ``done(result, error)`` runs in the GUI thread."""
        if self.busy:
            return
        self.busy = True
        self.status.set(self.tr("running_now"))
        for b in buttons:
            b.state(["disabled"])

        def target():
            try:
                res, err = work(), None
            except Exception as exc:    # shown to the user, never silent
                res, err = None, exc

            def finish():
                self.busy = False
                self.status.set("")
                for b in buttons:
                    b.state(["!disabled"])
                done(res, err)
            self.q.put(("call", finish))
        threading.Thread(target=target, daemon=True).start()

    def _error(self, err):
        self.log_write(f"{self.tr('error')}: {err}")
        messagebox.showerror(self.tr("error"), str(err))

    def _pick_dir(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _pick_raster(self):
        p = filedialog.askopenfilename(filetypes=[("GeoTIFF", "*.tif *.tiff"), ("*", "*")])
        if p:
            self.m["raster"].set(p)

    def _refresh_selected(self):
        txt = self.selected["label"] if self.selected else self.tr("none_selected")
        self.sel_label.configure(text=txt)
        self.dl_area.configure(text=txt)

    def show_image(self, path):
        """Show a JPG/PNG in a new window (Pillow needed) and fall back to the default viewer."""
        try:
            from PIL import Image, ImageTk
            win = tk.Toplevel(self)
            win.title(str(path))
            im = Image.open(path)
            im.thumbnail((int(self.winfo_screenwidth() * .8), int(self.winfo_screenheight() * .8)))
            ph = ImageTk.PhotoImage(im)
            self.images.append(ph)
            ttk.Label(win, image=ph).pack()
            self.bind_text(ttk.Button(win, command=lambda: webbrowser.open(Path(path).as_uri())), "save_image").pack(pady=4)
        except Exception:
            webbrowser.open(Path(path).as_uri())

    # ---------------------------------------------------------------- actions
    def do_search(self):
        q = self.q.get().strip()
        if len(q) < 2:
            return
        from .geocode import search_area
        ft = FEATURE_TYPES[max(self.ft_box.current(), 0)] or None
        cc = self.cc.get().strip() or None
        self.log_write(self.tr("searching"))

        def done(res, err):
            if err:
                return self._error(err)
            self.places = res
            self.tree.delete(*self.tree.get_children())
            for i, p in enumerate(res):
                self.tree.insert("", "end", iid=str(i), values=(p.name, p.kind or p.category,
                                 "polygon" if p.has_polygon else "bbox", p.display_name))
            if res:
                self.tree.selection_set("0")
        self.run_bg(lambda: search_area(q, limit=8, country_codes=cc, feature_type=ft), done, [self.btn_search])

    def _current_place(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("geedownload", self.tr("pick_first"))
            return None
        return self.places[int(sel[0])]

    def use_area(self):
        p = self._current_place()
        if p:
            self.selected = {"label": p.display_name, "place": p}
            self._refresh_selected()
            self.nb.select(1)

    def save_shp(self):
        p = self._current_place()
        if not p:
            return
        folder = filedialog.askdirectory()
        if not folder:
            return
        from .aoi import aoi_from_place
        from .boundary import save_boundary

        def done(res, err):
            self._error(err) if err else self.log_write(f"{self.tr('done')}: {res}")
        self.run_bg(lambda: save_boundary(aoi_from_place(p), folder), done)

    def _area_arg(self):
        bb = self.v["bbox"].get().strip()
        if bb:
            vals = [float(x) for x in bb.replace(";", ",").replace(" ", ",").split(",") if x]
            if len(vals) != 4:
                raise ValueError(self.tr("need_area"))
            return vals
        if self.selected:
            from .aoi import aoi_from_place
            return aoi_from_place(self.selected["place"])
        raise ValueError(self.tr("need_area"))

    def do_download(self):
        try:
            area = self._area_arg()
            num = lambda k, cast=float: cast(self.v[k].get()) if self.v[k].get().strip() else None  # noqa: E731
            bands = [b for b in self.v["bands"].get().replace(",", " ").split() if b] or None
            red = REDUCERS[max(self.red_box.current(), 0)] or None
            kw = dict(bands=bands, cloud_max=num("cloud"), reducer=red, scale=num("scale"), crs=self.v["crs"].get().strip() or None,
                      clip=self.chk["clip"].get(), mask_clouds=self.chk["mask"].get(), apply_scale=self.chk["scale"].get(),
                      per_image=self.chk["per"].get(), max_images=num("maxn", int) or 10, buffer_m=num("buffer") or 0,
                      project=self.v["project"].get().strip() or None)
        except Exception as exc:
            return self._error(exc)
        out = Path(self.v["out"].get()).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        ds, start, end, want_map = self.ds_var.get(), self.v["start"].get().strip() or None, self.v["end"].get().strip() or None, self.chk["map"].get()

        def work():
            from .pipeline import download_area
            res = download_area(area, ds, start, end, out_dir=out, **kw)
            if want_map and res.stack:
                from .maps import plot_map, preview_args
                plot_map(res.stack, res.folder / "preview.jpg", area=res.shapefile, title=res.info["area"],
                         country=res.info.get("country"), **preview_args(res.info))
            return res

        def done(res, err):
            if err:
                return self._error(err)
            self.log_write(f"{self.tr('dl_done')} {res.folder}")
            prev = res.folder / "preview.jpg"
            if prev.exists():
                self.show_image(prev)
        self.run_bg(work, done, [self.btn_dl])

    def _map_out(self, default):
        return filedialog.asksaveasfilename(defaultextension=".jpg", initialfile=default, filetypes=[("JPG", "*.jpg"), ("PNG", "*.png")])

    def do_raster_map(self):
        raster = self.m["raster"].get().strip()
        if not raster:
            return messagebox.showinfo("geedownload", self.tr("need_raster"))
        out = self._map_out("map.jpg")
        if not out:
            return
        bands = [int(b) if b.isdigit() else b for b in self.m["bands"].get().replace(",", " ").split()] or None
        kw = dict(bands=bands, cmap=self.m_cmap.get() or "viridis", classes=self.m_classes.get() or None,
                  title=self.m["title"].get().strip() or None, country=self.m["country"].get().strip() or None,
                  dpi=int(self.m["dpi"].get() or 150))

        def work():
            from .maps import plot_map
            return plot_map(raster, out, **kw)
        self.run_bg(work, lambda r, e: self._error(e) if e else self.show_image(r))

    def do_area_map(self):
        name = self.m["a_name"].get().strip() or (self.selected["place"] if self.selected else "")
        if not name:
            return messagebox.showinfo("geedownload", self.tr("need_area"))
        out = self._map_out("area.jpg")
        if not out:
            return
        if isinstance(name, str):
            name = name
        kw = dict(country=self.m["a_country"].get().strip() or None, extent="country" if self.ext_box.current() == 1 else "area",
                  admin1=self.m_admin1.get(), dpi=int(self.m["dpi"].get() or 150))

        def work():
            from .aoi import aoi_from_place, resolve_aoi
            from .maps import plot_area
            area = resolve_aoi(name) if isinstance(name, str) else aoi_from_place(name)
            return plot_area(area, out, **kw)
        self.run_bg(work, lambda r, e: self._error(e) if e else self.show_image(r))


def launch(lang: str = "en") -> None:
    """Open the desktop GUI. ``lang`` is ``"ar"``, ``"fa"`` or ``"en"``."""
    App(lang).mainloop()


if __name__ == "__main__":
    launch(sys.argv[1] if len(sys.argv) > 1 else "en")
