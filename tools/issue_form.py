"""issue_form -- read a submission issue's body, as GitHub renders the form
in .github/ISSUE_TEMPLATE/submit-plugin.yml ("### Label", a blank line,
the answer).

The body is untrusted text: it comes in through an environment variable or
a file, never through the workflow's expressions, and only these fields
come out of it, each checked against a strict pattern.

    ISSUE_BODY=... python3 tools/issue_form.py      prints the fields as JSON

Standard library only.
"""
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
FORM = os.path.join(os.path.dirname(HERE), ".github", "ISSUE_TEMPLATE", "submit-plugin.yml")

LABELS = {"repo": "Repository", "tag": "Release tag", "description": "Short description", "rules": "Rules"}
RULES = 3                          # the form's checkboxes, all required
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}")
TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}")
NO_RESPONSE = "_No response_"


class FormError(ValueError):
    pass


def sections(body):
    """{label: answer text} for each '### label' in the body"""
    out, cur, lines = {}, None, []
    for line in body.replace("\r\n", "\n").split("\n"):
        m = re.fullmatch(r"### (.{1,80})", line.strip())
        if m:
            if cur is not None:
                out[cur] = "\n".join(lines).strip()
            cur, lines = m.group(1).strip(), []
        elif cur is not None:
            lines.append(line)
    if cur is not None:
        out[cur] = "\n".join(lines).strip()
    return out


def clean_line(s, n):
    """one line of plain text, at most n characters: no control or format
    characters, spaces collapsed"""
    s = "".join(" " if unicodedata.category(c)[0] in "CZ" else c for c in s)
    s = re.sub(r" +", " ", s).strip()
    if len(s) > n:
        raise FormError(f"the description is {len(s)} characters. The limit is {n}")
    return s


def parse(body, description_max=160):
    """the fields of a submission: {"repo", "tag", "description", "rules_ok"}"""
    if not isinstance(body, str) or len(body) > 20000:
        raise FormError("the issue body is missing or too long")
    s = sections(body)
    repo = s.get(LABELS["repo"], "").strip()
    repo = re.sub(r"^https://github\.com/", "", repo).strip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not REPO.fullmatch(repo):
        raise FormError("give the repo as owner/repo, like yourname/your-plugin")
    tag = s.get(LABELS["tag"], "").strip()
    if tag == NO_RESPONSE:
        tag = ""
    if tag and not TAG.fullmatch(tag):
        raise FormError("the release tag can only use A-Z, a-z, 0-9 and . _ + -")
    desc = s.get(LABELS["description"], "").strip()
    if desc == NO_RESPONSE:
        desc = ""
    desc = clean_line(desc, description_max)
    if not desc:
        raise FormError("the short description is empty")
    boxes = re.findall(r"^- \[([ xX])\] ", s.get(LABELS["rules"], ""), re.M)
    rules_ok = len(boxes) >= RULES and all(b in "xX" for b in boxes)
    return {"repo": repo, "tag": tag, "description": desc, "rules_ok": rules_ok}


def main():
    try:
        print(json.dumps(parse(os.environ.get("ISSUE_BODY", ""))))
    except FormError as e:
        print(json.dumps({"error": str(e)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
