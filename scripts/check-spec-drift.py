#!/usr/bin/env python3
"""Claim-level spec-vs-code gate for thesada-doc.

This site is the specification, not a retelling of one. A page that says the
firmware does X is asserting something checkable, so the assertion carries a
machine-readable anchor and this script proves it against the source repo.

A claim is an HTML comment on the line(s) directly above the prose it covers:

    <!-- claim: repo=thesada-fw file=lib/thesada-core/src/Identity.h
         match="static const char\\* deviceId" -->
    `device_id` is minted on first boot and never leaves NVS.

Keys:

    repo    required, must be a key in scripts/spec-sources.json
    file    required, path inside that repo
    ref     optional, git ref to read (default: the repo's ref in the map)
    match   optional, Python regex that MUST appear in the file
    absent  optional, Python regex that MUST NOT appear in the file
    deployed optional, CalVer YY.0M.MICRO; every fleet channel in the repo's
            `deployed` map must offer at least this version, read live from
            the OTA manifests. A ref proves the code exists; this proves it
            ships. Only repos with a `deployed` map accept it.
    why     optional, free text, ignored by the checker, read by humans

With neither match nor absent, the claim asserts only that the file exists.

Sources resolve in this order, so it runs the same locally and in CI:

    1. $SPEC_SRC_DIR/<repo>       explicit override
    2. ../<repo>                  sibling checkout (the normal dev layout)
    3. a shallow clone under $SPEC_CACHE_DIR (default .spec-cache/)

Exit codes: 0 all claims hold, 1 a claim failed, 2 the checker could not run
(bad annotation, unreachable source repo). A missing source is never a silent
pass.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "scripts" / "spec-sources.json"
CACHE = Path(os.environ.get("SPEC_CACHE_DIR", ROOT / ".spec-cache"))
SKIP_DIRS = {"_site", "vendor", ".git", ".jekyll-cache", "node_modules", ".spec-cache"}

CLAIM_RE = re.compile(r"<!--\s*claim:\s*(.*?)\s*-->", re.DOTALL)
# key=value where value is bare or double-quoted. Quoted wins, so a regex may
# hold spaces and equals signs.
KV_RE = re.compile(r'(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|(\S+))')

KNOWN_KEYS = {"repo", "file", "ref", "match", "absent", "deployed", "why"}
CALVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class Fail(Exception):
    """A claim that did not hold. Message is the operator-facing line."""


class Broken(Exception):
    """The checker could not evaluate a claim. Never reported as a pass."""


def load_sources():
    try:
        return json.loads(SOURCES.read_text())
    except FileNotFoundError:
        raise Broken(f"missing {SOURCES.relative_to(ROOT)}")
    except json.JSONDecodeError as e:
        raise Broken(f"{SOURCES.relative_to(ROOT)} is not valid JSON: {e}")


def git(args, cwd=None):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, check=False
    )


def resolve_repo(name, spec):
    """Return a directory holding a git checkout of `name`, cloning if needed."""
    override = os.environ.get("SPEC_SRC_DIR")
    candidates = []
    if override:
        candidates.append(Path(override) / name)
    candidates.append(ROOT.parent / name)

    for path in candidates:
        if (path / ".git").exists():
            return path

    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / name
    if not (dest / ".git").exists():
        r = git(["clone", "--filter=blob:none", "--no-checkout", spec["url"], str(dest)])
        if r.returncode != 0:
            raise Broken(f"cannot clone {name}: {r.stderr.strip().splitlines()[-1:]}")
    return dest


def read_at_ref(repo_dir, ref, path):
    """File contents at a ref, or None when the path is absent there."""
    r = git(["show", f"{ref}:{path}"], cwd=repo_dir)
    if r.returncode != 0:
        err = r.stderr.strip()
        # Distinguish "no such ref" (checker cannot run) from "no such path"
        # (the claim is wrong, which is the whole point of the gate).
        if "unknown revision" in err or "not a tree object" in err or "bad revision" in err:
            raise Broken(f"ref {ref!r} not available in {repo_dir.name}: fetch it first")
        return None
    return r.stdout


def parse_claim(raw, where):
    fields = {}
    consumed = []
    for m in KV_RE.finditer(raw):
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else m.group(3)
        if m.group(2) is not None:
            val = val.replace('\\"', '"')
        if key in fields:
            raise Broken(f"{where}: duplicate key {key!r}")
        fields[key] = val
        consumed.append(m.span())

    # Anything the key=value scan did not consume is a typo, and a typo that
    # silently drops an assertion (`match=` with no value) downgrades the claim
    # to a file-exists check while still reporting success.
    leftover, last = [], 0
    for start, end in consumed:
        leftover.append(raw[last:start])
        last = end
    leftover.append(raw[last:])
    junk = "".join(leftover).strip()
    if junk:
        raise Broken(f"{where}: unparsed text in claim: {junk[:60]!r}")

    unknown = set(fields) - KNOWN_KEYS
    if unknown:
        raise Broken(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")
    for required in ("repo", "file"):
        if required not in fields:
            raise Broken(f"{where}: missing required key {required!r}")
    return fields


def check_claim(fields, where, sources, fetched, manifests):
    repo = fields["repo"]
    if repo not in sources:
        raise Broken(f"{where}: unknown repo {repo!r}, add it to spec-sources.json")

    spec = sources[repo]
    ref = fields.get("ref", spec["ref"])
    path = fields["file"]

    repo_dir = resolve_repo(repo, spec)
    key = (repo, ref)
    if key not in fetched:
        # Fetch once per (repo, ref). A sibling checkout can be arbitrarily
        # stale, and a gate that passes on stale code is not a gate - so a
        # failed fetch must not fall through to whatever a previous run left
        # in refs/spec-drift.
        r = git(["fetch", "--quiet", spec["url"], f"+{ref}:refs/spec-drift/{repo}/{ref}"],
                cwd=repo_dir)
        if r.returncode != 0:
            raise Broken(
                f"cannot fetch {ref!r} from {repo}: {r.stderr.strip().splitlines()[-1:]}"
            )
        fetched[key] = f"refs/spec-drift/{repo}/{ref}"
    resolved = fetched[key]

    body = read_at_ref(repo_dir, resolved, path)
    if body is None:
        raise Fail(f"{path} does not exist in {repo}@{ref}")

    if "match" in fields:
        try:
            pattern = re.compile(fields["match"], re.MULTILINE)
        except re.error as e:
            raise Broken(f"{where}: match is not a valid regex: {e}")
        if not pattern.search(body):
            raise Fail(f"{repo}@{ref}:{path} does not contain /{fields['match']}/")

    if "absent" in fields:
        try:
            pattern = re.compile(fields["absent"], re.MULTILINE)
        except re.error as e:
            raise Broken(f"{where}: absent is not a valid regex: {e}")
        hit = pattern.search(body)
        if hit:
            line = body[: hit.start()].count("\n") + 1
            raise Fail(
                f"{repo}@{ref}:{path}:{line} contains /{fields['absent']}/, "
                "which this page says is not there"
            )

    if "deployed" in fields:
        check_deployed(fields, where, spec, manifests)


def calver(text, where):
    """YY.0M.MICRO as a comparable tuple. Anything else cannot be compared."""
    m = CALVER_RE.match(text.strip())
    if not m:
        raise Broken(f"{where}: {text!r} is not a CalVer YY.0M.MICRO version")
    return tuple(int(g) for g in m.groups())


def fetch_manifest(url, manifests):
    """Live OTA manifest as a dict. Unreachable is Broken, never a pass."""
    if url in manifests:
        return manifests[url]
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        raise Broken(f"cannot read OTA manifest {url}: {e}")
    if "version" not in data:
        raise Broken(f"OTA manifest {url} carries no version field")
    manifests[url] = data
    return data


def check_deployed(fields, where, spec, manifests):
    """Every fleet channel must offer at least the claimed version."""
    dep = spec.get("deployed")
    if not dep:
        raise Broken(f"{where}: repo {fields['repo']!r} has no deployed map in spec-sources.json")
    if not isinstance(dep.get("boards"), list) or not isinstance(dep.get("manifest"), str):
        raise Broken(f"{where}: deployed map for {fields['repo']!r} needs a manifest template and a boards list")
    want = calver(fields["deployed"], where)
    behind = []
    for board in dep["boards"]:
        url = dep["manifest"].format(board=board)
        live = fetch_manifest(url, manifests)
        if calver(str(live["version"]), url) < want:
            behind.append(f"{board}={live['version']}")
    if behind:
        raise Fail(
            f"claims firmware {fields['deployed']} is deployed, but the fleet offers "
            + ", ".join(behind)
        )


def markdown_files():
    """Readable tracked markdown. Some pages are symlinks into a private repo,
    so they dangle on a fresh checkout; skip those instead of crashing."""
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if not path.is_file():
            print(
                f"check-spec-drift: skipping unreadable {path.relative_to(ROOT)}",
                file=sys.stderr,
            )
            continue
        yield path


def main():
    try:
        sources = load_sources()
    except Broken as e:
        print(f"check-spec-drift: {e}", file=sys.stderr)
        return 2

    failures, broken, checked = [], [], 0
    fetched, manifests = {}, {}

    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for m in CLAIM_RE.finditer(text):
            line = text[: m.start()].count("\n") + 1
            where = f"{rel}:{line}"
            checked += 1
            try:
                fields = parse_claim(m.group(1), where)
                check_claim(fields, where, sources, fetched, manifests)
            except Fail as e:
                failures.append((where, str(e)))
            except Broken as e:
                broken.append(str(e))

    if broken:
        print("check-spec-drift: could not evaluate:", file=sys.stderr)
        for msg in broken:
            print(f"  {msg}", file=sys.stderr)

    if failures:
        print("check-spec-drift: the code does not back these claims:", file=sys.stderr)
        for where, msg in failures:
            print(f"  {where}", file=sys.stderr)
            print(f"    {msg}", file=sys.stderr)
        print(
            "\nEither the page is out of date, or the claim anchor is. Fix the one "
            "that is wrong.\nA page describing unbuilt work must say so in the prose "
            "and drop the match= assertion.",
            file=sys.stderr,
        )

    if broken:
        return 2
    if failures:
        return 1
    print(f"check-spec-drift: ok ({checked} claim(s) verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
