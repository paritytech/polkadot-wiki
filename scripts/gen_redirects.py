#!/usr/bin/env python3
"""Generate client-side redirect stubs for GitHub Pages from scripts/_redirects.

GitHub Pages has no server-side redirects, so the Netlify-style `_redirects`
rules are materialised two ways:

  * Concrete rules  -> one meta-refresh stub at <site>/<old>/index.html.
  * Wildcard rules  -> a prefix-matching fallback injected into <site>/404.html
                       (GitHub Pages serves 404.html for any unmatched path).

The old Polkadot Wiki was Docusaurus with `routeBasePath: "docs"`, so every
`/*/<page>` rule resolves to the real old URL `/docs/<page>`; the leading `*`
is expanded accordingly.

Internal targets are written as RELATIVE URLs (from each stub's own location)
so redirects resolve correctly whether the site is served at the root
(wiki.polkadot.com) or under a project-page subpath
(paritytech.github.io/polkadot-wiki/). Cross-site targets are absolute.

Never clobbers a real built page.
"""
import argparse, html, os, posixpath, re

BASE = "docs"  # Docusaurus routeBasePath


def is_external(url):
    return bool(re.match(r"^https?://", url))


def parse_redirects(path):
    """Yield (old_url, target, is_wildcard) from a Netlify _redirects file."""
    for line in open(path):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 2:
            continue
        src, dst = parts[0], parts[1]
        # expand the leading single-segment wildcard to the real base path
        if src.startswith("/*/"):
            old = "/%s/%s" % (BASE, src[3:])
        elif src == "/*":
            old = "/%s" % BASE
        else:
            old = src
        wildcard = ("*" in old) or bool(re.search(r"/:", old))
        yield old, dst, wildcard


def rel_target(old_key, new_value):
    """Relative path from the stub at /<old>/ to an internal target <new>."""
    old = old_key.strip("/")
    new = new_value.strip("/")
    rel = posixpath.relpath(new or ".", old or ".")
    if new_value.endswith("/") and not rel.endswith("/"):
        rel += "/"
    return rel


def write_stub(site_dir, old, target):
    out_dir = os.path.join(site_dir, old.strip("/"))
    index = os.path.join(out_dir, "index.html")
    if os.path.exists(index):  # real page wins; never overwrite
        return False
    t = html.escape(target)
    os.makedirs(out_dir, exist_ok=True)
    with open(index, "w") as f:
        f.write(
            '<!doctype html><html><head><meta charset="utf-8">'
            "<title>Redirecting…</title>"
            f'<meta http-equiv="refresh" content="0; url={t}">'
            f'<link rel="canonical" href="{t}">'
            '<meta name="robots" content="noindex">'
            f'<script>location.replace("{t}")</script></head>'
            f'<body>Redirecting to <a href="{t}">{t}</a></body></html>'
        )
    return True


def wildcard_prefix(old):
    """The literal path (below /docs/) up to the first * or :placeholder."""
    rest = old[len("/%s/" % BASE):]  # strip leading /docs/
    return re.split(r"[*]|/:", rest, maxsplit=1)[0].split(":")[0]


def inject_404(site_dir, wildcards):
    """Inject a prefix-matching redirect fallback into site/404.html."""
    path = os.path.join(site_dir, "404.html")
    if not os.path.exists(path):
        print("404.html not found; skipping wildcard fallback")
        return
    # most-specific (longest prefix) first
    rules = sorted(
        ({"pfx": wildcard_prefix(o), "t": d, "ext": is_external(d)} for o, d, _ in wildcards),
        key=lambda r: len(r["pfx"]),
        reverse=True,
    )
    import json
    script = (
        "<script>(function(){"
        "var p=location.pathname,i=p.indexOf('/%s/');" % BASE
        + "if(i<0)return;"
        "var base=p.slice(0,i),rest=p.slice(i+%d);" % (len(BASE) + 2)
        + "var rules=%s;" % json.dumps(rules, separators=(",", ":"))
        + "for(var k=0;k<rules.length;k++){if(rest.indexOf(rules[k].pfx)===0){"
        "location.replace(rules[k].ext?rules[k].t:base+rules[k].t);return;}}"
        "})();</script>"
    )
    doc = open(path).read()
    if "</head>" in doc:
        doc = doc.replace("</head>", script + "</head>", 1)
    else:
        doc += script
    open(path, "w").write(doc)
    print("404.html: injected %d wildcard prefix rules" % len(rules))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="site")
    ap.add_argument("--redirects", default="scripts/_redirects")
    a = ap.parse_args()

    concrete = wildcards = written = skipped = 0
    wild_rules = []
    for old, dst, is_wild in parse_redirects(a.redirects):
        if is_wild:
            wildcards += 1
            wild_rules.append((old, dst, is_wild))
            continue
        concrete += 1
        target = dst if is_external(dst) else rel_target(old, dst)
        if write_stub(a.site_dir, old, target):
            written += 1
        else:
            skipped += 1
    print(f"concrete rules: {concrete} (wrote {written} stubs, skipped {skipped} real pages)")
    print(f"wildcard rules: {wildcards}")
    inject_404(a.site_dir, wild_rules)


if __name__ == "__main__":
    main()
