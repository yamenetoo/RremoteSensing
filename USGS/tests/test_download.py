import hashlib
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from usgs_splib07.download import (
    choose_file, download_file, download_splib07, extract_zip, list_remote_files,
)


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture()
def server():
    payload = make_zip({"ASCIIdata/ASCIIdata_splib07b/a.txt": "x" * 5000, "photos/p.jpg": "jpg"})
    state = {"range_requests": 0, "fail_once": True}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            base = f"http://127.0.0.1:{self.server.server_port}"
            if self.path.startswith("/catalog/item/"):
                body = {"title": "root", "files": [
                    {"name": "usgs_splib07.zip", "size": 10**9, "url": base + "/big.zip"}]}
            elif self.path.startswith("/catalog/items"):
                body = {"items": [{"title": "child", "files": [{
                    "name": "ASCIIdata_splib07b.zip", "size": len(payload), "url": base + "/f.zip",
                    "checksum": {"value": hashlib.md5(payload).hexdigest(), "type": "MD5"}}]}]}
            elif self.path == "/f.zip":
                start = 0
                rng = self.headers.get("Range")
                if rng:
                    state["range_requests"] += 1
                    start = int(rng.split("=")[1].split("-")[0])
                data = payload[start:]
                self.send_response(206 if rng else 200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if state["fail_once"] and not rng:  # cut the first transfer in half
                    state["fail_once"] = False
                    self.wfile.write(data[: len(data) // 2])
                    self.wfile.flush()
                    self.connection.close()
                    return
                self.wfile.write(data)
                return
            else:
                self.send_error(404)
                return
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}", state, payload
    srv.shutdown()


def test_list_and_choose(server):
    base, _, _ = server
    files = list_remote_files(base_url=base)
    assert {f.name for f in files} == {"usgs_splib07.zip", "ASCIIdata_splib07b.zip"}
    assert choose_file(files, "ASCIIdata_splib07b").name == "ASCIIdata_splib07b.zip"
    with pytest.raises(LookupError):
        choose_file(files, "does_not_exist")


def test_download_resume_checksum_and_extract(server, tmp_path, monkeypatch):
    from usgs_splib07 import download as dl
    monkeypatch.setattr(dl, "CHUNK", 512)  # small chunks so partial data is written before the cut
    base, state, payload = server
    out = download_splib07(tmp_path, base_url=base)
    assert (out / "ASCIIdata" / "ASCIIdata_splib07b" / "a.txt").read_text() == "x" * 5000
    assert not (out / "photos").exists()  # only ASCIIdata extracted
    assert state["range_requests"] >= 1  # the cut transfer was resumed, not restarted
    assert (tmp_path / "downloads" / "ASCIIdata_splib07b.zip").read_bytes() == payload


def test_corrupt_download_detected(server, tmp_path):
    base, state, payload = server
    state["fail_once"] = False
    f = [x for x in list_remote_files(base_url=base) if x.name.startswith("ASCII")][0]
    f.checksum = "0" * 32  # wrong on purpose
    with pytest.raises(IOError):
        download_file(f, tmp_path)
    assert not (tmp_path / f.name).exists()


def test_zip_slip_blocked(tmp_path):
    z = tmp_path / "evil.zip"
    z.write_bytes(make_zip({"../escape.txt": "boom"}))
    with pytest.raises(ValueError):
        extract_zip(z, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()
