"""Streamlit app: data, browse, preprocess, compare, about, in English / Arabic / Persian.

Start with ``splib07 gui`` (do not run this file directly).
"""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import usgs_splib07 as splib
from usgs_splib07 import preprocess as pp
from usgs_splib07.gui.i18n import LANGS, RTL, t
from usgs_splib07.gui.logic import NORMALIZE_METHODS, STEP_KEYS, build_steps, parse_spectrum, validate_params

ASSETS = Path(__file__).with_name("assets")
MAX_PLOT = 10
MAX_OPTIONS = 500
SENSOR_CHOICES = ["sentinel2a", "landsat8", "aster", "custom"]
STEP_LABEL = {"clip": "st_clip", "smooth": "st_smooth", "derivative": "st_derivative", "continuum": "st_continuum",
              "snv": "st_snv", "normalize": "st_normalize", "to_sensor": "st_sensor"}

st.set_page_config(page_title="USGS splib07", page_icon=str(ASSETS / "icon.png"), layout="wide")

# ------------------------------------------------------------------ language
if "lang" not in st.session_state:
    q = st.query_params.get("lang")
    first = q if q in LANGS else os.environ.get("USGS_SPLIB07_GUI_LANG", "en")
    st.session_state["lang"] = first if first in LANGS else "en"
lang = st.sidebar.selectbox("Language / اللغة / زبان", list(LANGS), format_func=LANGS.get, key="lang")
T = lambda key, **kw: t(key, lang, **kw)  # noqa: E731

if lang in RTL:
    st.markdown(
        """<style>
        .stApp, [data-testid="stSidebar"] {direction: rtl;}
        .stApp {font-family: "Vazirmatn","Noto Naskh Arabic","Segoe UI",Tahoma,Arial,sans-serif;}
        [data-testid="stDataFrame"], [data-testid="stVegaLiteChart"], .stCode, code {direction: ltr;}
        </style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ helpers
def chart(wl_list, series: dict, height: int = 340):
    """Line chart; ``series`` maps a legend name to values (one wavelength array per series in ``wl_list``)."""
    frames = [pd.DataFrame({"x": wl, "y": y, "name": name}) for (name, y), wl in zip(series.items(), wl_list)]
    df = pd.concat(frames, ignore_index=True)
    c = (alt.Chart(df).mark_line(strokeWidth=1.6)
         .encode(x=alt.X("x:Q", title=T("wavelength"), scale=alt.Scale(zero=False)),
                 y=alt.Y("y:Q", title=T("reflectance"), scale=alt.Scale(zero=False)),
                 color=alt.Color("name:N", legend=alt.Legend(orient="bottom", title=None, labelLimit=400)),
                 tooltip=["name:N", alt.Tooltip("x:Q", format=".0f"), alt.Tooltip("y:Q", format=".4f")])
         .properties(height=height).interactive())
    st.altair_chart(c, width="stretch")


def library_to_npz_bytes(lib) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        return Path(lib.save(Path(d) / "library.npz")).read_bytes()


def set_library(lib, label: str):
    st.session_state["lib"] = lib
    st.session_state["lib_label"] = label
    st.session_state.pop("processed", None)


# ------------------------------------------------------------------ initial library
if "lib" not in st.session_state:
    env_lib = os.environ.get("USGS_SPLIB07_GUI_LIB")
    try:
        if env_lib:
            set_library(splib.SpectralLibrary.load(env_lib), Path(env_lib).name)
        else:
            set_library(splib.demo_library(step=5.0), T("src_demo"))
    except Exception as exc:  # pragma: no cover
        st.error(f"{T('error')}: {exc}")

st.title(T("app_title"))
st.caption(T("app_subtitle"))
tab_data, tab_browse, tab_pre, tab_cmp, tab_about = st.tabs(
    [T("tab_data"), T("tab_browse"), T("tab_pre"), T("tab_compare"), T("tab_about")])
lib = st.session_state.get("lib")

# ------------------------------------------------------------------ 1. data
with tab_data:
    src = st.radio(T("source"), ["demo", "usgs", "file"], format_func=lambda k: T("src_" + k), horizontal=True)
    try:
        if src == "demo":
            if st.button(T("btn_demo")):
                set_library(splib.demo_library(step=5.0), T("src_demo"))
        elif src == "usgs":
            chapters = st.multiselect(T("chapters"), list("MSCLOAV"), default=["M"], placeholder=T("choose"), format_func=lambda c: f"{c}: {T('ch_' + c)}")
            c1, c2 = st.columns(2)
            step = c1.number_input(T("grid_step"), 1.0, 50.0, 5.0, 1.0)
            home = c2.text_input(T("home_folder"), str(splib.default_home()))
            st.info(T("download_note"))
            if st.button(T("btn_load"), disabled=not chapters):
                with st.spinner(T("loading")):
                    set_library(splib.get_library(home, chapters=chapters, step=float(step)), "USGS splib07 " + "".join(chapters))
        else:
            up = st.file_uploader(T("upload_npz"), type=["npz"])
            if up is not None and st.session_state.get("_npz_name") != (up.name, up.size):
                set_library(splib.SpectralLibrary.load(io.BytesIO(up.getvalue())), up.name)
                st.session_state["_npz_name"] = (up.name, up.size)
    except Exception as exc:
        st.error(f"{T('error')}: {exc}")
    lib = st.session_state.get("lib")
    if lib is not None:
        st.success(T("loaded", n=len(lib), bands=lib.shape[1], lo=f"{lib.wavelengths[0]:.0f}", hi=f"{lib.wavelengths[-1]:.0f}"))
        st.caption(st.session_state.get("lib_label", ""))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(T("m_spectra"), len(lib))
        m2.metric(T("m_materials"), lib.meta["material"].nunique())
        m3.metric(T("m_bands"), lib.shape[1])
        m4.metric(T("m_range"), f"{lib.wavelengths[0]:.0f}-{lib.wavelengths[-1]:.0f}")

# ------------------------------------------------------------------ 2. browse
with tab_browse:
    if lib is None:
        st.info(T("no_library"))
    else:
        c1, c2, c3 = st.columns([2, 2, 2])
        text = c1.text_input(T("search"), "")
        chapters_avail = sorted(lib.meta["chapter"].unique()) if "chapter" in lib.meta else []
        fam_avail = sorted(lib.meta["family"].unique()) if "family" in lib.meta else []
        f_ch = c2.multiselect(T("filter_chapter"), chapters_avail, placeholder=T("choose"))
        f_fam = c3.multiselect(T("filter_family"), fam_avail, placeholder=T("choose"))
        mask = np.ones(len(lib), bool)
        if text:
            mask &= lib.meta["name"].str.contains(text, case=False, regex=False).to_numpy()
        if f_ch:
            mask &= lib.meta["chapter"].isin(f_ch).to_numpy()
        if f_fam:
            mask &= lib.meta["family"].isin(f_fam).to_numpy()
        idx = list(np.flatnonzero(mask))
        st.session_state["filtered_idx"] = idx
        st.write(T("found", n=len(idx)) + (" " + T("shown_first", k=MAX_OPTIONS) if len(idx) > MAX_OPTIONS else ""))
        cols = [c for c in ("name", "material", "chapter_name", "family") if c in lib.meta.columns]
        view = lib.meta.iloc[idx[:MAX_OPTIONS]][cols].rename(columns={"name": T("col_name"), "material": T("col_material"),
                                                                       "chapter_name": T("col_chapter"), "family": T("col_family")})
        st.dataframe(view, width="stretch", height=220)
        sig = f"{text}|{f_ch}|{f_fam}|{len(lib)}"
        sel = st.multiselect(T("select_plot", k=MAX_PLOT), idx[:MAX_OPTIONS], default=idx[:3], max_selections=MAX_PLOT, placeholder=T("choose"),
                             format_func=lambda i: str(lib.meta["name"].iloc[i]), key="sel_" + sig)
        st.session_state["selected_idx"] = sel
        if sel:
            chart([lib.wavelengths] * len(sel), {str(lib.meta["name"].iloc[i]): lib.X[i] for i in sel})
            st.download_button(T("dl_csv"), lib.select(mask=np.isin(np.arange(len(lib)), sel)).to_frame().to_csv(index=False).encode("utf-8"),
                               "spectra.csv", "text/csv")
        else:
            st.info(T("select_some"))

# ------------------------------------------------------------------ 3. preprocess
with tab_pre:
    if lib is None:
        st.info(T("no_library"))
    else:
        scope = st.radio(T("apply_to"), ["selected", "filtered"], format_func=lambda k: T("to_" + k), horizontal=True)
        chosen = st.session_state.get("selected_idx", []) if scope == "selected" else st.session_state.get("filtered_idx", [])
        selected_steps = st.multiselect(T("steps"), STEP_KEYS, format_func=lambda k: T(STEP_LABEL[k]), placeholder=T("choose"))
        P = {}
        if "smooth" in selected_steps or "derivative" in selected_steps:
            a, b = st.columns(2)
            P["window"] = a.number_input(T("p_window"), 3, 301, 11, 2)
            P["poly"] = b.number_input(T("p_poly"), 1, 7, 3)
        if "derivative" in selected_steps:
            P["order"] = st.number_input(T("p_order"), 1, 3, 1)
        if "normalize" in selected_steps:
            P["method"] = st.selectbox(T("p_method"), NORMALIZE_METHODS)
        if "to_sensor" in selected_steps:
            P["sensor"] = st.selectbox(T("p_sensor"), SENSOR_CHOICES, format_func=lambda s: T("p_custom") if s == "custom" else s)
            if P["sensor"] == "custom":
                a, b, c, d = st.columns(4)
                P["start"] = a.number_input(T("p_start"), 350.0, 2500.0, 400.0)
                P["stop"] = b.number_input(T("p_stop"), 350.0, 2500.0, 2400.0)
                P["spacing"] = c.number_input(T("p_spacing"), 1.0, 500.0, 10.0)
                P["fwhm"] = d.number_input(T("p_fwhm"), 1.0, 500.0, 10.0)
        if st.button(T("run")):
            problem = None if selected_steps else "no_steps"
            problem = problem or validate_params(selected_steps, P)
            if not chosen:
                st.info(T("select_some"))
            elif problem:
                st.warning(T(problem))
            else:
                try:
                    base = lib.select(mask=np.isin(np.arange(len(lib)), chosen))
                    st.session_state["processed"] = (base, base.pipeline(build_steps(selected_steps, P)))
                except Exception as exc:
                    st.error(f"{T('error')}: {exc}")
        if "processed" in st.session_state:
            before, after = st.session_state["processed"]
            st.caption(T("history") + ": " + " → ".join(after.history))
            n_show = min(MAX_PLOT, len(after))
            c1, c2 = st.columns(2)
            with c1:
                st.subheader(T("before"))
                chart([before.wavelengths] * n_show, {str(before.meta["name"].iloc[i]): before.X[i] for i in range(n_show)}, 300)
            with c2:
                st.subheader(T("after"))
                chart([after.wavelengths] * n_show, {str(after.meta["name"].iloc[i]): after.X[i] for i in range(n_show)}, 300)
            d1, d2 = st.columns(2)
            d1.download_button(T("dl_npz"), library_to_npz_bytes(after), "processed_library.npz")
            d2.download_button(T("dl_csv_proc"), after.to_frame().to_csv(index=False).encode("utf-8"), "processed_spectra.csv", "text/csv")

# ------------------------------------------------------------------ 4. compare
with tab_cmp:
    if lib is None:
        st.info(T("no_library"))
    else:
        st.write(T("cmp_intro"))
        up = st.file_uploader(T("upload_spec"), type=["csv", "txt", "tsv", "dat"], key="spec_file")
        pasted = st.text_area(T("paste_spec"), height=110)
        use_example = st.checkbox(T("example_spec"))
        k = st.slider(T("k_best"), 1, 15, 5)
        if st.button(T("btn_match")):
            try:
                if use_example:
                    rng = np.random.default_rng(0)
                    wl_q, y_q = lib.wavelengths, np.nan_to_num(lib.X[0]) * 0.7 + rng.normal(0, 0.01, lib.shape[1])
                elif up is not None:
                    wl_q, y_q = parse_spectrum(up.getvalue())
                else:
                    wl_q, y_q = parse_spectrum(pasted)
                res = lib.match(y_q, k=k, query_wavelengths=wl_q)
                st.session_state["match"] = (wl_q, y_q, res)
            except Exception as exc:
                st.error(T("parse_error", msg=str(exc)))
        if "match" in st.session_state:
            wl_q, y_q, res = st.session_state["match"]
            st.caption(T("angle_hint"))
            st.dataframe(res.rename(columns={"name": T("col_name"), "material": T("col_material"), "chapter": T("col_chapter"),
                                             "angle_deg": T("col_angle")}).drop(columns=["angle_rad"]), width="stretch")
            best = str(res["name"].iloc[0])
            st.subheader(T("overlay"))
            chart([wl_q, lib.wavelengths], {T("yours"): y_q, best: lib.spectrum(best)})

# ------------------------------------------------------------------ about
with tab_about:
    c1, c2 = st.columns([1, 4])
    c1.image(str(ASSETS / "icon.png"), width=140)
    with c2:
        st.write(T("about_text"))
        st.markdown(f"**{T('author')}:** {splib.__author__} · {splib.__email__}")
        st.markdown(f"**{T('version')}:** {splib.__version__} · {T('license')}")
        st.caption(T("data_credit"))
        st.caption(T("disclaimer"))
