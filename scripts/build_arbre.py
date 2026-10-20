"""Construit ARBRE.html : l'arbre interactif des plugins (couches Core / Extensions / Feuilles).

Lit les manifestes ``spectre/plugins/*/__init__.py`` (docstring, Plugin(...)), les injecte dans
``scripts/arbre_template.html`` et écrit ``ARBRE.html`` à la racine. Les couches cibles et les écarts
sont dans le gabarit (CORE, EXT, TARGET_DEPS, ECARTS) : ils suivent ARCHITECTURE.md § 3 et § 4.

    .venv/Scripts/python.exe scripts/build_arbre.py
"""
import ast
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def manifests():
    out = []
    for d in sorted((ROOT / "spectre" / "plugins").iterdir()):
        f = d / "__init__.py"
        if not f.exists():
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        info = {"name": d.name, "doc": ast.get_docstring(tree) or "", "depends_on": [], "title": "",
                "description": "", "required": False, "pages": [], "nav": []}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Plugin"):
                continue
            for kw in node.keywords:
                v = kw.value
                if kw.arg == "depends_on":
                    info["depends_on"] = [e.value for e in v.elts]
                elif kw.arg in ("title", "description", "required") and isinstance(v, ast.Constant):
                    info[kw.arg] = v.value
                elif kw.arg == "pages":
                    info["pages"] = [e.args[0].value for e in v.elts if isinstance(e, ast.Call) and e.args]
                elif kw.arg == "nav":
                    info["nav"] = [(e.args[0].value if e.args else
                                    next((k.value.value for k in e.keywords if k.arg == "label"), ""))
                                   for e in v.elts if isinstance(e, ast.Call)]
        info["files"] = sorted(p.name for p in d.iterdir() if p.suffix == ".py" and p.name != "__init__.py")
        kernel = set()
        for py in d.glob("*.py"):
            text = py.read_text(encoding="utf-8")
            for mod in re.findall(r"from \.{2,3}kernel\.(\w+) import", text):
                kernel.add(mod)
            for names in re.findall(r"from \.{2,3}kernel import ([^\n]+)", text):
                for n in names.split(","):
                    n = n.strip().split(" as ")[0].strip()
                    if n:
                        kernel.add(n)
            for mod in re.findall(r"spectre\.kernel\.(\w+)", text):
                kernel.add(mod)
        for html in (list((d / "pages").glob("*.html")) if (d / "pages").exists() else []) + list((d / "static").rglob("*.js") if (d / "static").exists() else []):
            for js in re.findall(r"/static/kernel/(\w+)\.js", html.read_text(encoding="utf-8", errors="ignore")):
                kernel.add("static/" + js + ".js")
        info["kernel"] = sorted(kernel)
        static = d / "static"
        info["static"] = sorted(p.name for p in static.glob("*.js")) if static.exists() else []
        out.append(info)
    return out


def main():
    data = json.dumps(manifests(), ensure_ascii=False)
    template = (ROOT / "scripts" / "arbre_template.html").read_text(encoding="utf-8")
    (ROOT / "ARBRE.html").write_text(template.replace("__DATA__", data), encoding="utf-8")
    print("ARBRE.html écrit")


if __name__ == "__main__":
    main()
