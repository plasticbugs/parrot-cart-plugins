"""sitecopy -- the site's words, read from site/copy.toml.

Every sentence the site shows, and the fixed sentences in the replies on
submission issues and pull requests, lives in site/copy.toml so it can be
edited without touching the code. A value is plain text with a little
Markdown, and everything else is escaped, so < and & are just characters:

    [text](url)   a link        `code`   code        **bold**   bold

{name} is a placeholder the code fills in (str.format_map); {{ and }} are
literal braces.

    T = sitecopy.COPY
    T.html("home.hero.lead")            for the page: Markdown rendered, the rest escaped
    T.attr("header.home_label")         for an attribute: escaped, no Markdown
    T.text("bot.checked", where=...)    as written (the bot's Markdown, or text the caller escapes)
    T.rows("home.install.steps", ("title", "text"))   an array of tables, each field as html
    T.list("authors.needs.columns")     an array of strings, each as html
    T.block("submit.check.command")     a code block: escaped, nothing else
    T.raw("authors.readme.sample")      a string, untouched

A missing key, an unknown placeholder or a stray brace stops the build
with the key's name. Standard library only (tomllib, Python 3.11+).
"""
import html
import os
import re
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "site", "copy.toml")
LINK = 'class="link"'

_INLINE = re.compile(r"`([^`\n]+)`|\*\*(.+?)\*\*|\[([^\]\n]+)\]\(([^()\s]+)\)")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


class CopyError(Exception):
    pass


def _esc(s):
    return html.escape(s, quote=False)


def inline(s, link=LINK):
    """s as HTML: `code`, **bold** and [text](url) rendered, everything else escaped.
    link is the attribute a link gets (None for a bare <a>)."""
    out, at = [], 0
    for m in _INLINE.finditer(s):
        out.append(_esc(s[at:m.start()]))
        code, bold, text, url = m.groups()
        if code is not None:
            out.append(f'<code class="code">{_esc(code)}</code>')
        elif bold is not None:
            out.append(f"<b>{inline(bold, link)}</b>")
        else:
            if _SCHEME.match(url) and not url.lower().startswith(("https://", "http://", "mailto:")):
                raise ValueError(f"the link {url} isn't a web address")
            attrs = f"{link} " if link else ""
            out.append(f'<a {attrs}href="{html.escape(url, quote=True)}">{inline(text, link)}</a>')
        at = m.end()
    out.append(_esc(s[at:]))
    return "".join(out)


class _Values(dict):
    def __init__(self, where, key, values):
        super().__init__(values)
        self.where, self.key = where, key

    def __missing__(self, name):
        ok = ", ".join("{" + k + "}" for k in sorted(self)) or "none"
        raise CopyError(f"{self.where}: {self.key} uses {{{name}}}, which isn't a placeholder it takes "
                        f"(it takes: {ok})")


class Copy:
    def __init__(self, path=PATH, data=None):
        self.path = path
        self._data = data

    @property
    def where(self):
        rel = os.path.relpath(self.path, ROOT)
        return self.path if rel.startswith("..") else rel

    def data(self):
        if self._data is None:
            try:
                with open(self.path, "rb") as f:
                    self._data = tomllib.load(f)
            except FileNotFoundError:
                raise CopyError(f"{self.where} is missing") from None
            except tomllib.TOMLDecodeError as e:
                raise CopyError(f"{self.where} isn't valid TOML: {e}") from None
        return self._data

    def keys(self):
        """every key that holds text or a list, as dotted names"""
        out = []

        def walk(node, pre):
            for k, v in node.items():
                if isinstance(v, dict):
                    walk(v, pre + k + ".")
                else:
                    out.append(pre + k)
        walk(self.data(), "")
        return out

    # ---- reading ----

    def _get(self, key):
        node = self.data()
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                raise CopyError(f"{self.where}: {key} is missing. Add it back (the site needs it)")
            node = node[part]
        return node

    def _str(self, key, v=None):
        v = self._get(key) if v is None else v
        if not isinstance(v, str):
            raise CopyError(f"{self.where}: {key} should be text in quotes")
        return v

    def _fill(self, key, s, values):
        try:
            return s.format_map(_Values(self.where, key, values))
        except CopyError:
            raise
        except (ValueError, IndexError, AttributeError, KeyError, TypeError) as e:
            raise CopyError(f"{self.where}: {key}: {e}. A placeholder is a {{name}}, and a brace on its own "
                            "is written {{ or }}") from None

    def _html(self, key, s, values, link=LINK):
        try:
            return self._fill(key, inline(s, link), values)
        except ValueError as e:
            raise CopyError(f"{self.where}: {key}: {e}") from None

    # ---- the forms the pages and the bot use ----

    def raw(self, key):
        return self._str(key)

    def text(self, key, **values):
        return self._fill(key, self._str(key), values)

    def html(self, key, _link=LINK, **values):
        return self._html(key, self._str(key), values, _link)

    def attr(self, key, **values):
        return self._fill(key, _esc(self._str(key)).replace('"', "&quot;"), values)

    def block(self, key):
        return _esc(self._str(key))

    def list(self, key, **values):
        v = self._get(key)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise CopyError(f"{self.where}: {key} should be a list of text in quotes")
        return [self._html(f"{key}[{i}]", x, values) for i, x in enumerate(v, 1)]

    def texts(self, key, **values):
        v = self._get(key)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise CopyError(f"{self.where}: {key} should be a list of text in quotes")
        return [self._fill(f"{key}[{i}]", x, values) for i, x in enumerate(v, 1)]

    def rows(self, key, fields, **values):
        v = self._get(key)
        if not isinstance(v, list) or not v or not all(isinstance(x, dict) for x in v):
            raise CopyError(f"{self.where}: {key} should be one or more [[{key}]] blocks")
        out = []
        for i, item in enumerate(v, 1):
            row = []
            for f in fields:
                where = f"{key} (block {i}).{f}"
                if f not in item:
                    raise CopyError(f"{self.where}: {where} is missing. Add it back (the site needs it)")
                row.append(self._html(where, self._str(where, item[f]), values))
            out.append(tuple(row))
        return out


COPY = Copy()
