#!/usr/bin/env python3
"""SEO and link gate over a built static site. Stdlib only.

usage: site-check.py <site-dir> --base https://example.org [--skip GLOB ...]

Every HTML page needs a lang, title, meta description, canonical under --base,
og:title and og:image, and valid JSON-LD if it has any. sitemap.xml and
robots.txt must exist, robots must not block the site, and every sitemap URL
must resolve to a built file. Internal links and assets must resolve too.
Pages marked noindex, meta refreshes and --skip globs only get the link check.
Exit 1 lists every failure.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

LINK_ATTRS = {"a": "href", "link": "href", "img": "src", "script": "src", "source": "src", "video": "src"}
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = None
        self.meta = {}
        self.canonical = None
        self.links = []
        self.ld = []
        self._in_title = self._in_ld = self._in_svg = False
        self._head_done = False
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "svg":
            self._in_svg = True
        elif tag == "body":
            self._head_done = True
        elif tag == "title" and self.title is None and not self._in_svg and not self._head_done:
            self._in_title, self.title = True, ""
        elif tag == "meta":
            key = a.get("name") or a.get("property") or a.get("http-equiv")
            if key:
                self.meta.setdefault(key.lower(), (a.get("content") or "").strip())
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld, self._buf = True, ""
        if tag == "link" and "canonical" in (a.get("rel") or "").split():
            self.canonical = a.get("href")
        elif tag in LINK_ATTRS and a.get(LINK_ATTRS[tag]):
            if tag == "link" and not {"stylesheet", "icon", "manifest", "preload", "apple-touch-icon"} & set((a.get("rel") or "").split()):
                return
            self.links.append(a[LINK_ATTRS[tag]])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "svg":
            self._in_svg = False
        elif tag == "head":
            self._head_done = True
        elif tag == "script" and self._in_ld:
            self._in_ld = False
            self.ld.append(self._buf)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_ld:
            self._buf += data


def resolve(root, path):
    """The built file a site path serves, Cloudflare Pages style, or None."""
    path = urllib.parse.unquote(path).lstrip("/")
    full = os.path.normpath(os.path.join(root, path))
    if not full.startswith(os.path.normpath(root)):
        return None
    for cand in (full, os.path.join(full, "index.html"), full + ".html"):
        if os.path.isfile(cand):
            return cand
    return None


def site_path(root, page_file, ref, base):
    """Site-absolute path for a link on page_file, or None when external."""
    ref = ref.strip()
    if ref.startswith(base + "/") or ref == base:
        ref = ref[len(base):] or "/"
    if not ref or ref.startswith("#") or EXTERNAL.match(ref):
        return None
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    if not ref:
        return None
    if ref.startswith("/"):
        return ref
    page_dir = "/" + os.path.relpath(os.path.dirname(page_file), root)
    return urllib.parse.urljoin(page_dir.rstrip("/.") + "/", ref)


def check(root, base, skips):
    root = os.path.abspath(root)
    base = base.rstrip("/")
    fails, pages, links = [], 0, 0

    for name in ("sitemap.xml", "robots.txt"):
        if not os.path.isfile(os.path.join(root, name)):
            fails.append(f"{name}: missing")
    robots = os.path.join(root, "robots.txt")
    if os.path.isfile(robots):
        agent_all = False
        for line in open(robots, encoding="utf-8"):
            k, _, v = line.partition(":")
            k, v = k.strip().lower(), v.strip()
            if k == "user-agent":
                agent_all = v == "*"
            elif k == "disallow" and agent_all and v == "/":
                fails.append("robots.txt: disallows the whole site")
    sitemap = os.path.join(root, "sitemap.xml")
    if os.path.isfile(sitemap):
        try:
            locs = [e.text.strip() for e in ET.parse(sitemap).iter() if e.tag.endswith("loc") and e.text]
        except ET.ParseError as e:
            fails.append(f"sitemap.xml: {e}")
            locs = []
        if not locs:
            fails.append("sitemap.xml: no URLs")
        for loc in locs:
            if not loc.startswith(base + "/"):
                fails.append(f"sitemap.xml: {loc} is not under {base}")
            elif not resolve(root, loc[len(base):]):
                fails.append(f"sitemap.xml: {loc} has no built page")

    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".html"):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, root)
            p = Page()
            p.feed(open(full, encoding="utf-8", errors="replace").read())
            pages += 1
            for ref in p.links:
                sp = site_path(root, full, ref, base)
                if sp is None:
                    continue
                links += 1
                if not resolve(root, sp):
                    fails.append(f"{rel}: broken link {ref}")
            skipped = any(fnmatch.fnmatch(rel, g) for g in skips)
            if skipped or "noindex" in p.meta.get("robots", "") or "refresh" in p.meta:
                continue
            if not p.lang:
                fails.append(f"{rel}: no lang on <html>")
            if not (p.title or "").strip():
                fails.append(f"{rel}: no <title>")
            if not p.meta.get("description"):
                fails.append(f"{rel}: no meta description")
            if not p.canonical:
                fails.append(f"{rel}: no canonical")
            elif not p.canonical.startswith(base + "/"):
                fails.append(f"{rel}: canonical {p.canonical} is not under {base}")
            for key in ("og:title", "og:image"):
                if not p.meta.get(key):
                    fails.append(f"{rel}: no {key}")
            img = p.meta.get("og:image", "")
            if img.startswith(base + "/") and not resolve(root, img[len(base):]):
                fails.append(f"{rel}: og:image {img} has no built file")
            for ld in p.ld:
                try:
                    json.loads(ld)
                except ValueError as e:
                    fails.append(f"{rel}: JSON-LD does not parse: {e}")

    if pages == 0:
        fails.append("no HTML pages found")
    return fails, pages, links


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site")
    ap.add_argument("--base", required=True, help="canonical origin, e.g. https://example.org")
    ap.add_argument("--skip", action="append", default=[], help="glob of pages exempt from the tag checks")
    args = ap.parse_args()
    fails, pages, links = check(args.site, args.base, args.skip)
    for f in fails:
        print(f"FAIL {f}")
    print(f"site-check: {pages} pages, {links} internal links, {len(fails)} failures")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
