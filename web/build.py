"""Build the static site (GitHub Pages): the web app with the game running in the browser.

    python -m web.build [--out _site]

* ``static/``: the app's own files (``server/static``, without the design mockups) plus
  ``local.js`` and ``worker.js``, which replace the server.
* ``index.html``: the app's page with relative paths and ``window.STATIC_SITE`` set.
* ``api/bots.json``, ``api/insights.json``: what the server would answer for those requests.
* ``py/app.zip``: the Python the worker runs under Pyodide (``flip7``, the rooms and bot registry
  from ``server``, ``web/browser.py``) and every ``models/*.pt`` network exported to ``.npz``.

Reading the checkpoints needs torch; the built site doesn't.
"""
import argparse
import glob
import json
import os
import shutil
import tempfile
import zipfile

from flip7.infer import export
from server import insights
from server.bots import Registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_FILES = ["flip7/*.py", "server/__init__.py", "server/rooms.py", "server/bots.py", "web/__init__.py", "web/browser.py"]


def build(out):
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(ROOT, "server", "static"), os.path.join(out, "static"),
                    ignore=shutil.ignore_patterns("mockups"))
    for name in ("local.js", "worker.js"):
        shutil.copy(os.path.join(ROOT, "web", name), os.path.join(out, "static", name))

    with open(os.path.join(ROOT, "server", "static", "index.html")) as f:
        page = f.read()
    app_tag = '<script src="/static/app.js" type="module"></script>'
    assert app_tag in page
    page = page.replace(app_tag, '<script>window.STATIC_SITE = true;</script>\n' + app_tag)
    page = page.replace('"/static/', '"static/')
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(page)

    with tempfile.TemporaryDirectory() as tmp:
        models = os.path.join(tmp, "models")
        os.makedirs(models)
        for ckpt in sorted(glob.glob(os.path.join(ROOT, "models", "*.pt"))):
            export(ckpt, os.path.join(models, os.path.basename(ckpt)[:-3] + ".npz"))
        os.makedirs(os.path.join(out, "api"))
        with open(os.path.join(out, "api", "bots.json"), "w") as f:
            json.dump(Registry(models).catalog(), f)
        with open(os.path.join(out, "api", "insights.json"), "w") as f:
            json.dump(insights.load(os.path.join(ROOT, "analysis")), f)

        os.makedirs(os.path.join(out, "py"))
        with zipfile.ZipFile(os.path.join(out, "py", "app.zip"), "w", zipfile.ZIP_DEFLATED) as z:
            for pattern in PY_FILES:
                for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
                    z.write(path, os.path.relpath(path, ROOT))
            for path in sorted(glob.glob(os.path.join(models, "*.npz"))):
                z.write(path, os.path.join("models", os.path.basename(path)))

    open(os.path.join(out, ".nojekyll"), "w").close()  # serve the files as they are


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    a = ap.parse_args()
    build(a.out)
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(a.out) for f in fs)
    print(f"built {a.out} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
