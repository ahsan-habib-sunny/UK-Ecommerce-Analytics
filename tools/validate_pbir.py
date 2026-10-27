"""Validate every PBIR JSON file against the schema URL in its own $schema field (remote $refs resolved)."""
import json, pathlib, sys, urllib.request
from jsonschema import Draft7Validator, Draft202012Validator
from referencing import Registry, Resource

CACHE = {}

def fetch(uri):
    uri = uri.split("#")[0]
    if uri not in CACHE:
        with urllib.request.urlopen(uri, timeout=30) as r:
            CACHE[uri] = json.loads(r.read().decode("utf-8-sig"))
    return CACHE[uri]

def retrieve(uri):
    return Resource.from_contents(fetch(uri))

registry = Registry(retrieve=retrieve)
root = pathlib.Path(sys.argv[1])
bad = 0
files = [p for p in root.rglob("*.json") if "/.pbi/" not in p.as_posix() and "StaticResources" not in p.as_posix()]
for p in sorted(files):
    doc = json.loads(p.read_text(encoding="utf-8"))
    url = doc.get("$schema")
    if not url:
        continue
    schema = fetch(url)
    cls = Draft202012Validator if "2020-12" in schema.get("$schema", "") else Draft7Validator
    errs = sorted(cls(schema, registry=registry).iter_errors(doc), key=lambda e: list(e.path))
    if errs:
        bad += 1
        print(f"FAIL {p.relative_to(root)}")
        for e in errs[:5]:
            print("   ", "/".join(map(str, e.path)), "->", e.message[:300])
print(f"\n{len(files)} files checked, {bad} with schema errors")
