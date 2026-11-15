"""markdown -- an author's Markdown (a README.md, a release's notes) as safe
HTML for the site.

GitHub-flavoured: headings, paragraphs, emphasis, strikethrough, code spans,
fenced and indented code, block quotes, bullet, numbered and task lists,
tables, rules, links (inline, reference, <auto> and bare), and images.

It is written to be safe by construction rather than cleaned afterwards:

  - Every tag in the output is one this file writes itself (TAGS below);
    the author's text only ever goes through html.escape().
  - Raw HTML in the source is dropped (comments, <script> and <style> with
    what they hold, and every other tag; its text stays). Inside code it is
    shown as text.
  - The only attribute an author's text reaches is href, and only as an
    https URL: a relative link is resolved against the repository at the
    release's tag, and anything else (javascript:, data:, http:, //host)
    leaves the link's text without a link.
  - Images are never embedded, so the site hotlinks nothing: an image is a
    link saying "Image: alt".

    render(text, base="https://github.com/owner/repo/blob/v1.0.0/", level=3)

level is the tag a "# heading" gets (3: <h3>), so a README sits under the
page's own headings. Standard library only.
"""
import html
import re
import urllib.parse

TAGS = {"h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "em", "strong", "del", "code", "pre", "blockquote",
        "ul", "ol", "li", "a", "table", "thead", "tbody", "tr", "th", "td", "input"}
ATTRS = {"a": {"href", "rel"}, "input": {"type", "disabled", "checked"}, "th": {"class"}, "td": {"class"},
         "li": {"class"}, "ul": {"class"}, "ol": {"start"}}
MAX_DEPTH = 6

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_RULE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_ITEM = re.compile(r"^( {0,3})([-*+]|\d{1,9}[.)])( +|$)(.*)$")
_DEF = re.compile(r"^ {0,3}\[([^\]\n]{1,200})\]:[ \t]*<?([^\s>]+)>?(?:[ \t]+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?[ \t]*$")
_DELIM = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_RAW = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)|<(https://[^\s<>]+)>|<!--.*?(?:-->|\Z)|"
                  r"<(script|style)\b.*?(?:</\4\s*>|\Z)|<br\s*/?>|</?[A-Za-z][^<>]*>", re.S | re.I)


def _strip_html(text):
    """drop raw HTML outside code spans; <https://...> autolinks stay"""
    def sub(m):
        if m.group(1) or m.group(3):
            return m.group(0)
        return "\n" if m.group(0).lower().startswith("<br") else ""
    return _RAW.sub(sub, text)


class _Renderer:
    def __init__(self, base, level, anchor):
        self.base, self.level, self.anchor = base, level, anchor
        self.defs = {}
        self.slots = []

    # ---- links ----

    def url(self, raw):
        """an https URL for href, already escaped, or None"""
        u = html.unescape(raw.strip())
        if not u or re.search(r"[\x00-\x20\x7f\"'<>`\\]", u):
            return None
        if u.startswith("#"):
            return html.escape(self.anchor + u, quote=True) if self.anchor else None
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", u):
            return html.escape(u, quote=True) if u.lower().startswith("https://") and len(u) > 8 else None
        if u.startswith("//") or not self.base:
            return None
        full = urllib.parse.urljoin(self.base, u[1:] if u.startswith("/") else u)
        root = self.base.split("/blob/")[0] + "/"
        if not full.startswith(root):
            return None
        return html.escape(full, quote=True)

    def slot(self, markup):
        self.slots.append(markup)
        return f"\x00{len(self.slots) - 1}\x00"

    def link(self, text_html, raw_url):
        href = self.url(raw_url)
        if href is None:
            return text_html
        return f'<a href="{href}" rel="nofollow noopener">{text_html}</a>'

    # ---- inline ----

    def inline(self, s, links=True):
        # code spans first: nothing inside them is markup
        def code(m):
            body = m.group(2).replace("\n", " ")
            if body[:1] == " " == body[-1:] and body.strip():
                body = body[1:-1]
            return self.slot(f"<code>{html.escape(body)}</code>")
        s = re.sub(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", code, s, flags=re.S)
        s = re.sub(r"\\([!-/:-@\[-`{-~])", lambda m: self.slot(html.escape(m.group(1))), s)

        dest = r"\(\s*<?([^\s()<>]*(?:\([^\s()<>]*\)[^\s()<>]*)*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"

        def image(m):
            alt = html.escape(re.sub(r"\s+", " ", m.group(1)).strip())
            label = f"Image: {alt}" if alt else "Image"
            href = self.url(m.group(2))
            if href is None or not links:
                return self.slot(f"[{label[0].lower() + label[1:]}]")
            return self.slot(f'<a href="{href}" rel="nofollow noopener">{label}</a>')
        s = re.sub(r"!\[([^\]]*)\]" + dest, image, s)

        def image_ref(m):
            alt = html.escape(re.sub(r"\s+", " ", m.group(1)).strip())
            return self.slot(f"[image: {alt}]" if alt else "[image]")
        s = re.sub(r"!\[([^\]]*)\](?:\[[^\]]*\])?", image_ref, s)

        if links:
            inner = r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]"
            s = re.sub(inner + dest, lambda m: self.slot(self.link(self.inline(m.group(1), False), m.group(2))), s)

            def ref(m):
                key = re.sub(r"\s+", " ", (m.group(2) or m.group(1))).strip().lower()
                if key not in self.defs:
                    return m.group(0)
                return self.slot(self.link(self.inline(m.group(1), False), self.defs[key]))
            s = re.sub(inner + r"(?:\[([^\]]*)\])?", ref, s)
            s = re.sub(r"<(https://[^\s<>]+)>",
                       lambda m: self.slot(self.link(html.escape(m.group(1)), m.group(1))), s)

            def bare(m):
                u = m.group(0)
                tail = ""
                while u and u[-1] in ".,;:!?'\"*_~" or (u.endswith(")") and u.count(")") > u.count("(")):
                    tail, u = u[-1] + tail, u[:-1]
                return self.slot(self.link(html.escape(u), u)) + tail
            s = re.sub(r"(?<![\w/])https://[^\s<>\x00]+", bare, s)

        s = html.escape(s, quote=False)
        # (a run of emphasis is at most 400 characters, so a hostile file can't make these slow)
        s = re.sub(r"\*\*(?=\S)(.{1,400}?)(?<=\S)\*\*", r"<strong>\1</strong>", s, flags=re.S)
        s = re.sub(r"(?<![\w_])__(?=\S)(.{1,400}?)(?<=\S)__(?![\w_])", r"<strong>\1</strong>", s, flags=re.S)
        s = re.sub(r"\*(?=[^\s*])(.{1,400}?)(?<=[^\s*])\*", r"<em>\1</em>", s, flags=re.S)
        s = re.sub(r"(?<![\w_])_(?=[^\s_])(.{1,400}?)(?<=[^\s_])_(?![\w_])", r"<em>\1</em>", s, flags=re.S)
        s = re.sub(r"~~(?=\S)(.{1,400}?)(?<=\S)~~", r"<del>\1</del>", s, flags=re.S)
        s = re.sub(r"(?: {2,}|\\)\n", "<br>\n", s)
        return s

    def fill(self, s):
        """put the finished pieces back (they may hold pieces themselves)"""
        for _ in range(MAX_DEPTH + 2):
            if "\x00" not in s:
                break
            s = re.sub(r"\x00(\d+)\x00", lambda m: self.slots[int(m.group(1))], s)
        return s.replace("\x00", "")

    # ---- blocks ----

    def cells(self, line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith("\\|"):
            line = line[:-1]
        return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", line)]

    def table(self, head, delim, rows):
        aligns = []
        for c in self.cells(delim):
            aligns.append(' class="ta-c"' if c.startswith(":") and c.endswith(":") else
                          ' class="ta-r"' if c.endswith(":") else "")
        n = len(aligns)
        out = ["<table><thead><tr>"]
        out += [f"<th{aligns[i]}>{self.inline(c)}</th>" for i, c in enumerate(self.cells(head)[:n])]
        out.append("</tr></thead><tbody>")
        for r in rows:
            cs = (self.cells(r) + [""] * n)[:n]
            out.append("<tr>" + "".join(f"<td{aligns[i]}>{self.inline(c)}</td>" for i, c in enumerate(cs)) + "</tr>")
        out.append("</tbody></table>")
        return "".join(out)

    def blocks(self, lines, depth=0):
        out, i, n = [], 0, len(lines)
        para = []

        def flush():
            if para:
                out.append("<p>" + self.inline("\n".join(x.strip() for x in para)) + "</p>")
                para.clear()

        while i < n:
            line = lines[i]
            if not line.strip():
                flush()
                i += 1
                continue
            m = _FENCE.match(line)
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                flush()
                mark, body = m.group(1), []
                i += 1
                while i < n and not re.match(r"^ {0,3}" + re.escape(mark[0]) + "{" + str(len(mark)) + r",}[ \t]*$",
                                             lines[i]):
                    body.append(lines[i])
                    i += 1
                i += 1
                out.append("<pre><code>" + html.escape("\n".join(body)) + "</code></pre>")
                continue
            m = _HEADING.match(line)
            if m:
                flush()
                h = min(6, self.level + len(m.group(1)) - 1)
                out.append(f"<h{h}>{self.inline(m.group(2) or '')}</h{h}>")
                i += 1
                continue
            if para and re.match(r"^ {0,3}(=+|-+)[ \t]*$", line):
                h = min(6, self.level + (0 if "=" in line else 1))
                text = self.inline("\n".join(x.strip() for x in para))
                para.clear()
                out.append(f"<h{h}>{text}</h{h}>")
                i += 1
                continue
            if _RULE.match(line):
                flush()
                out.append("<hr>")
                i += 1
                continue
            if re.match(r"^ {0,3}>", line):
                flush()
                body = []
                while i < n and lines[i].strip() and (re.match(r"^ {0,3}>", lines[i]) or body):
                    body.append(re.sub(r"^ {0,3}> ?", "", lines[i]))
                    i += 1
                inner = self.blocks(body, depth + 1) if depth < MAX_DEPTH else html.escape("\n".join(body))
                out.append(f"<blockquote>{inner}</blockquote>")
                continue
            if "|" in line and i + 1 < n and _DELIM.match(lines[i + 1]) and "-" in lines[i + 1] \
                    and len(self.cells(line)) == len(self.cells(lines[i + 1])) and not para:
                head, delim, rows = line, lines[i + 1], []
                i += 2
                while i < n and lines[i].strip() and "|" in lines[i]:
                    rows.append(lines[i])
                    i += 1
                out.append(self.table(head, delim, rows))
                continue
            m = _ITEM.match(line)
            if m and not (para and m.group(2)[0].isdigit() and m.group(2)[:-1] != "1"):
                flush()
                i = self.list(lines, i, out, depth)
                continue
            if not para and re.match(r"^ {4,}\S", line):
                body = []
                while i < n and (re.match(r"^ {4}", lines[i]) or not lines[i].strip()):
                    body.append(lines[i][4:])
                    i += 1
                while body and not body[-1].strip():
                    body.pop()
                out.append("<pre><code>" + html.escape("\n".join(body)) + "</code></pre>")
                continue
            para.append(line)
            i += 1
        flush()
        return "\n".join(out)

    def list(self, lines, i, out, depth):
        n = len(lines)
        first = _ITEM.match(lines[i])
        ordered = first.group(2)[0].isdigit()
        kind = first.group(2)[-1] if ordered else first.group(2)
        items, loose, gap = [], False, False
        while i < n:
            m = _ITEM.match(lines[i])
            if not m or (m.group(2)[0].isdigit() != ordered) or (m.group(2)[-1] if ordered else m.group(2)) != kind \
                    or _RULE.match(lines[i]):
                break
            loose, gap = loose or gap, False
            pad = len(m.group(1)) + len(m.group(2)) + (len(m.group(3)) if 1 <= len(m.group(3)) <= 4 else 1)
            body = [m.group(4) if len(m.group(3)) <= 4 else " " * (len(m.group(3)) - 1) + m.group(4)]
            i += 1
            while i < n:
                if not lines[i].strip():
                    k = i
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and len(lines[k]) - len(lines[k].lstrip(" ")) >= pad:
                        body += [""] * (k - i)
                        i = k
                        continue
                    gap = True                             # loose, if the list goes on after it
                    break
                ind = len(lines[i]) - len(lines[i].lstrip(" "))
                if ind >= pad:
                    body.append(lines[i][pad:])
                elif _ITEM.match(lines[i]) or _HEADING.match(lines[i]) or _FENCE.match(lines[i]) \
                        or _RULE.match(lines[i]) or re.match(r"^ {0,3}>", lines[i]):
                    break
                else:
                    body.append(lines[i].strip())          # a lazy continuation line
                i += 1
            items.append(body)
            while i < n and not lines[i].strip():
                i += 1
        tag = "ol" if ordered else "ul"
        start = ""
        if ordered and first.group(2)[:-1].lstrip("0") not in ("1", ""):
            start = f' start="{int(first.group(2)[:-1])}"'
        tasks = False
        rendered = []
        for body in items:
            box = ""
            t = re.match(r"^\[([ xX])\][ \t]+", body[0])
            if t:
                tasks = True
                box = '<input type="checkbox" disabled' + (" checked" if t.group(1) in "xX" else "") + "> "
                body[0] = body[0][t.end():]
            inner = self.blocks(body, depth + 1) if depth < MAX_DEPTH else html.escape("\n".join(body))
            if not loose and inner.startswith("<p>") and inner.count("<p>") == 1:
                inner = inner.replace("<p>", "", 1).replace("</p>", "", 1)
            elif box and inner.startswith("<p>"):
                inner, box = "<p>" + box + inner[3:], ""
            rendered.append(f'<li{" class=" + chr(34) + "task" + chr(34) if t else ""}>{box}{inner}</li>')
        cls = ' class="tasks"' if tasks and not ordered else ""
        out.append(f"<{tag}{cls}{start}>" + "".join(rendered) + f"</{tag}>")
        return i


def render(text, base=None, level=3, anchor=None):
    """Markdown text as HTML. base: where relative links go (a GitHub
    .../blob/<tag>/ URL, or None to leave them as text); anchor: the page a
    "#section" link goes to; level: the heading tag for "#"."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    text = "".join(c for c in text if c == "\n" or (ord(c) >= 32 and ord(c) != 127))
    r = _Renderer(base, max(2, min(6, level)), anchor)
    # fenced code keeps its text; everything else loses its raw HTML
    lines, keep, fence = [], [], None
    for line in text.split("\n"):
        m = _FENCE.match(line)
        if fence is None and m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            lines += _strip_html("\n".join(keep)).split("\n") if keep else []
            keep, fence = [], m.group(1)
            lines.append(line)
        elif fence is not None:
            lines.append(line)
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$", line):
                fence = None
        else:
            keep.append(line)
    lines += _strip_html("\n".join(keep)).split("\n") if keep else []
    # link definitions, outside code
    body, fence = [], None
    for line in lines:
        m = _FENCE.match(line)
        if fence is None and m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = m.group(1)
        elif fence is not None:
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$", line):
                fence = None
        else:
            d = _DEF.match(line)
            if d:
                r.defs.setdefault(re.sub(r"\s+", " ", d.group(1)).strip().lower(), d.group(2))
                continue
        body.append(line)
    return r.fill(r.blocks(body))
