"""lint_workflows -- the registry's rules for its GitHub Actions workflows,
offline, standard library only.

    python3 tests/lint_workflows.py

Checks every .github/workflows/*.yml:
  - actions pinned by a full commit SHA, with the version in a comment
  - no ${{ }} inside a run step (values reach scripts through env)
  - no event text from issues, comments or pull requests anywhere
    (titles, bodies, branch names): the scripts fetch what they need
  - no pull_request_target or workflow_run triggers
  - permissions: {} at the top, and each job lists its own
  - a timeout on every job
  - checkout without saved credentials in jobs that can't write
  - every script a run step names exists and is executable
and the issue form against tools/issue_form.py and registry.config.json.
If actionlint is on the PATH it runs too.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


# ---- a small YAML reader: block maps, lists, block scalars, quoted and flow scalars ----

def _strip_comment(line):
    out, q = [], None
    for i, c in enumerate(line):
        if q:
            if c == q:
                q = None
        elif c in "\"'" and (i == 0 or line[i - 1] in " :[{,-"):
            q = c
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(c)
    return "".join(out).rstrip()


def _scalar(s):
    s = s.strip()
    if not s:
        return None
    if s[0] == '"' and s[-1] == '"':
        return json.loads(s)
    if s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if s == "{}":
        return {}
    if s == "[]":
        return []
    if s[0] == "[" and s[-1] == "]":
        return [_scalar(x) for x in s[1:-1].split(",") if x.strip()]
    if s[0] == "{" and s[-1] == "}":
        out = {}
        for part in s[1:-1].split(","):
            if part.strip():
                k, v = part.split(":", 1)
                out[k.strip()] = _scalar(v)
        return out
    if s in ("true", "false"):
        return s == "true"
    if s in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


class Yaml:
    def __init__(self, text):
        self.raw = text.split("\n")
        self.i = 0

    def _next(self):
        """(index, indent, content) of the next line with content, without moving"""
        j = self.i
        while j < len(self.raw):
            c = _strip_comment(self.raw[j])
            if c.strip():
                return j, len(c) - len(c.lstrip(" ")), c.strip()
            j += 1
        return None

    def parse(self):
        n = self._next()
        return self._block(n[1]) if n else None

    def _block(self, indent):
        n = self._next()
        if n is None or n[1] < indent:
            return None
        return self._list(n[1]) if n[2].startswith("- ") or n[2] == "-" else self._map(n[1])

    def _block_scalar(self, style, indent):
        lines = []
        while self.i < len(self.raw):
            line = self.raw[self.i]
            if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
                break
            lines.append(line)
            self.i += 1
        body = [l for l in lines]
        while body and not body[-1].strip():
            body.pop()
        ind = min((len(l) - len(l.lstrip(" ")) for l in body if l.strip()), default=0)
        body = [l[ind:] for l in body]
        if style.startswith(">"):
            text = " ".join(l.strip() for l in body if l.strip())
        else:
            text = "\n".join(body)
        return text + ("" if style.endswith("-") else "\n")

    def _value(self, rest, indent):
        if rest in ("|", "|-", ">", ">-", "|+", ">+"):
            return self._block_scalar(rest, indent)
        if rest == "":
            n = self._next()
            if n and (n[1] > indent or (n[1] == indent and n[2].startswith("- "))):
                return self._block(n[1])
            return None
        return _scalar(rest)

    def _map(self, indent):
        out = {}
        while True:
            n = self._next()
            if n is None or n[1] < indent:
                return out
            j, ind, c = n
            if ind > indent:
                raise ValueError(f"line {j + 1}: unexpected indent")
            if c.startswith("- "):
                return out
            m = re.match(r"((?:\"[^\"]*\")|(?:'[^']*')|[^:]+?):(?:\s+(.*))?$", c)
            if not m:
                raise ValueError(f"line {j + 1}: not a key: {c}")
            key = _scalar(m.group(1))
            self.i = j + 1
            out[key] = self._value((m.group(2) or "").strip(), indent)

    def _list(self, indent):
        out = []
        while True:
            n = self._next()
            if n is None or n[1] < indent or not (n[2].startswith("- ") or n[2] == "-"):
                return out
            j, ind, c = n
            if ind > indent:
                raise ValueError(f"line {j + 1}: unexpected indent")
            rest = c[2:].strip()
            if re.match(r"[A-Za-z_][\w-]*:(\s|$)", rest):
                # "- key: value": a map whose first key is on the dash's line
                self.raw[j] = " " * (indent + 2) + rest
                self.i = j
                out.append(self._map(indent + 2))
            else:
                self.i = j + 1
                out.append(self._value(rest, indent))


def load(path):
    with open(path) as f:
        return Yaml(f.read()).parse()


# ---- the rules ----

UNTRUSTED = re.compile(r"github\.event\.(issue\.(title|body)|comment\.|review|pull_request\.(title|body|head\.ref|head\.label)"
                       r"|discussion|pages|commits|head_commit)|github\.head_ref")
PIN = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")


def lint_workflow(path):
    bad = []
    rel = os.path.relpath(path, ROOT)
    with open(path) as f:
        text = f.read()
    for k, line in enumerate(text.split("\n"), 1):
        if UNTRUSTED.search(line):
            bad.append(f"{rel}:{k}: uses event text from an issue, comment or pull request")
        m = re.search(r"uses:\s*(\S+)", line)
        if m and not m.group(1).startswith("./"):
            if not PIN.fullmatch(m.group(1)):
                bad.append(f"{rel}:{k}: {m.group(1)} isn't pinned by a commit SHA")
            elif not re.search(r"#\s*v\d", line):
                bad.append(f"{rel}:{k}: say which version the SHA is, in a comment")
    w = load(path)
    on = w.get("on", w.get(True))
    triggers = on if isinstance(on, dict) else {t: None for t in (on if isinstance(on, list) else [on])}
    for t in ("pull_request_target", "workflow_run"):
        if t in triggers:
            bad.append(f"{rel}: the {t} trigger runs untrusted code with secrets")
    if w.get("permissions") not in ({}, {"contents": "read"}):
        bad.append(f"{rel}: the top-level permissions must be {{}} (or contents: read)")
    for name, job in (w.get("jobs") or {}).items():
        where = f"{rel}: job {name}"
        if w.get("permissions") == {} and "permissions" not in job:
            bad.append(f"{where}: no permissions of its own")
        if "timeout-minutes" not in job:
            bad.append(f"{where}: no timeout-minutes")
        perms = job.get("permissions") or {}
        writes = any(v == "write" for v in perms.values()) if isinstance(perms, dict) else perms == "write-all"
        for step in job.get("steps") or []:
            run = step.get("run")
            if run is not None and "${{" in str(run):
                bad.append(f"{where}: an expression inside run: {str(run).strip()[:60]}")
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                creds = (step.get("with") or {}).get("persist-credentials")
                if not writes and creds is not False:
                    bad.append(f"{where}: checkout keeps its credentials in a job that doesn't write")
            if isinstance(run, str):
                for script in re.findall(r"(?:^|\s)(tools/ci/[\w.-]+\.sh)", run):
                    p = os.path.join(ROOT, script)
                    if not os.path.isfile(p) or not os.access(p, os.X_OK):
                        bad.append(f"{where}: {script} is missing or not executable")
                for script in re.findall(r"python3(?: -I)? ((?:tools|tests)/[\w/.-]+\.py)", run):
                    if not os.path.isfile(os.path.join(ROOT, script)):
                        bad.append(f"{where}: {script} is missing")
    return bad


def lint_form():
    import issue_form
    bad = []
    path = issue_form.FORM
    rel = os.path.relpath(path, ROOT)
    form = load(path)
    with open(os.path.join(ROOT, "registry.config.json")) as f:
        config = json.load(f)
    if config["labels"]["submission"] not in (form.get("labels") or []):
        bad.append(f"{rel}: its labels don't include {config['labels']['submission']} (registry.config.json)")
    fields = {b.get("id"): b for b in form.get("body") or [] if b.get("id")}
    for key, label in issue_form.LABELS.items():
        b = fields.get(key)
        if b is None:
            bad.append(f"{rel}: no field with id {key}")
        elif (b.get("attributes") or {}).get("label") != label:
            bad.append(f"{rel}: field {key} is labelled {b['attributes'].get('label')!r}; issue_form.py reads {label!r}")
    rules = ((fields.get("rules") or {}).get("attributes") or {}).get("options") or []
    if len(rules) != issue_form.RULES or not all(r.get("required") for r in rules):
        bad.append(f"{rel}: {len(rules)} rules; issue_form.py expects {issue_form.RULES}, all required")
    for wf in ("submission.yml",):
        with open(os.path.join(ROOT, ".github", "workflows", wf)) as f:
            if f"'{config['labels']['submission']}'" not in f.read():
                bad.append(f".github/workflows/{wf}: doesn't check the {config['labels']['submission']} label")
    return bad


def main():
    d = os.path.join(ROOT, ".github", "workflows")
    files = sorted(os.path.join(d, n) for n in os.listdir(d) if n.endswith((".yml", ".yaml")))
    bad = []
    for p in files:
        bad += lint_workflow(p)
    bad += lint_form()
    tool = shutil.which("actionlint")
    if tool:
        r = subprocess.run([tool, "-no-color"] + files, capture_output=True, text=True)
        if r.returncode:
            bad += r.stdout.strip().split("\n")
    for b in bad:
        print(b)
    print(f"{len(files)} workflows and the issue form: " + ("ok" if not bad else f"{len(bad)} problems")
          + ("" if tool else " (actionlint isn't installed: the registry's own rules only)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
