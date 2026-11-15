"""ghapi -- the few read-only GitHub REST calls the registry makes.

Nothing here writes to GitHub. Every response is capped in size, redirects
are followed by hand (only to GitHub's own hosts, and the token is never
sent to another host), and a recorded transport replays saved responses so
the tests run without a network.

Standard library only.
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
USER_AGENT = "parrotcart-plugins-registry"
JSON_MAX = 2 * 1024 * 1024
HOSTS = {"api.github.com", "github.com", "codeload.github.com"}
HOST_SUFFIXES = (".githubusercontent.com",)


class GitHubError(Exception):
    """a failure worth retrying later (network, rate limit, 5xx)"""


class TooBig(Exception):
    pass


class Refused(Exception):
    """a URL this tool won't fetch (not GitHub's, not https)"""


def host_ok(url):
    u = urllib.parse.urlsplit(url)
    h = (u.hostname or "").lower()
    return u.scheme == "https" and (h in HOSTS or h.endswith(HOST_SUFFIXES))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpTransport:
    """urllib, one request at a time: get(url, headers, cap) ->
    (status, headers, body bytes); body None if it was over cap"""

    def __init__(self, timeout=30):
        self.timeout = timeout
        self.opener = urllib.request.build_opener(_NoRedirect)

    def get(self, url, headers, cap):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            r = self.opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            r = e
        except (urllib.error.URLError, OSError) as e:
            raise GitHubError(f"couldn't reach {urllib.parse.urlsplit(url).hostname}: {e}") from None
        with r:
            status = r.status if hasattr(r, "status") else r.code
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            if status in (301, 302, 303, 307, 308):
                return status, hdrs, b""
            n = hdrs.get("content-length")
            if n and n.isdigit() and int(n) > cap:
                return status, hdrs, None
            body = r.read(cap + 1)
            return status, hdrs, None if len(body) > cap else body


class RecordedTransport:
    """Replays a scenario: a folder with index.json mapping URL ->
    {"status": 200, "file": "x.json"} (or "body": {...}, or "location": url,
    "headers": {...}). URLs not in it are 404. Records what was asked."""

    def __init__(self, folder, extra=None):
        self.folder = folder
        with open(os.path.join(folder, "index.json")) as f:
            self.index = json.load(f)
        self.index.update(extra or {})
        self.asked = []

    def get(self, url, headers, cap):
        self.asked.append((url, dict(headers)))
        e = self.index.get(url)
        if e is None:
            return 404, {}, b'{"message": "Not Found"}'
        status = e.get("status", 200)
        hdrs = {k.lower(): v for k, v in e.get("headers", {}).items()}
        if "location" in e:
            hdrs["location"] = e["location"]
            return status, hdrs, b""
        if "file" in e:
            path = e["file"]
            if not os.path.isabs(path):
                path = os.path.normpath(os.path.join(self.folder, path))
            with open(path, "rb") as f:
                body = f.read()
        else:
            body = json.dumps(e.get("body", {})).encode()
        return status, hdrs, None if len(body) > cap else body


class RecordingTransport:
    """HttpTransport, saving every response into folder as a scenario that
    RecordedTransport replays (tools/record_fixture.py)"""

    def __init__(self, folder, inner=None):
        self.folder, self.inner, self.index = folder, inner or HttpTransport(), {}
        os.makedirs(folder, exist_ok=True)

    def get(self, url, headers, cap):
        status, hdrs, body = self.inner.get(url, headers, cap)
        e = {"status": status}
        keep = {k: hdrs[k] for k in ("location", "x-ratelimit-remaining") if k in hdrs}
        if "location" in keep:
            e["location"] = keep.pop("location")
        if keep:
            e["headers"] = keep
        if body is not None and "location" not in e:
            name = f"{len(self.index):02d}.json" if body[:1] in (b"{", b"[") else f"{len(self.index):02d}.bin"
            with open(os.path.join(self.folder, name), "wb") as f:
                f.write(body)
            e["file"] = name
        self.index[url] = e
        with open(os.path.join(self.folder, "index.json"), "w") as f:
            json.dump(self.index, f, indent=2)
            f.write("\n")
        return status, hdrs, body


class GitHub:
    def __init__(self, token=None, transport=None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN") or None
        self.t = transport or HttpTransport()

    def _get(self, url, accept, cap):
        """GET with redirects followed by hand: (status, body)"""
        for _ in range(5):
            if not host_ok(url):
                raise Refused(f"refused to fetch {url}: not a GitHub https URL")
            h = {"User-Agent": USER_AGENT, "Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
            if self.token and urllib.parse.urlsplit(url).hostname == "api.github.com":
                h["Authorization"] = f"Bearer {self.token}"
            status, hdrs, body = self.t.get(url, h, cap)
            if status in (301, 302, 303, 307, 308):
                loc = hdrs.get("location")
                if not loc:
                    raise GitHubError(f"{url}: a redirect without a location")
                url = urllib.parse.urljoin(url, loc)
                continue
            if body is None:
                raise TooBig(url)
            if (status == 403 and hdrs.get("x-ratelimit-remaining") == "0") or status == 429:
                raise GitHubError("GitHub's rate limit was reached: try again later")
            if status >= 500:
                raise GitHubError(f"GitHub answered {status} for {url}")
            return status, body
        raise GitHubError(f"too many redirects from {url}")

    def json(self, path):
        """GET API path -> parsed JSON, or None for 404"""
        status, body = self._get(API + path, "application/vnd.github+json", JSON_MAX)
        if status == 404:
            return None
        if status != 200:
            raise GitHubError(f"GitHub answered {status} for {path}")
        try:
            return json.loads(body)
        except ValueError:
            raise GitHubError(f"GitHub sent something that isn't JSON for {path}") from None

    @staticmethod
    def q(s):
        if s in (".", "..") or not s:
            raise ValueError(f"not a name GitHub has: {s!r}")
        return urllib.parse.quote(s, safe="")

    def repo(self, full):
        o, r = full.split("/")
        return self.json(f"/repos/{self.q(o)}/{self.q(r)}")

    def release(self, full, tag=None):
        o, r = full.split("/")
        if tag:
            return self.json(f"/repos/{self.q(o)}/{self.q(r)}/releases/tags/{self.q(tag)}")
        return self.json(f"/repos/{self.q(o)}/{self.q(r)}/releases/latest")

    def license(self, full, ref=None):
        o, r = full.split("/")
        path = f"/repos/{self.q(o)}/{self.q(r)}/license"
        if ref:
            path += "?ref=" + self.q(ref)
        return self.json(path)

    def readme(self, full, ref=None, cap=512 * 1024):
        """the README's text (None if there's none), at ref if given"""
        o, r = full.split("/")
        path = f"/repos/{self.q(o)}/{self.q(r)}/readme"
        if ref:
            path += "?ref=" + self.q(ref)
        d = self.json(path)
        if d is None:
            return None, None
        if d.get("encoding") != "base64" or not isinstance(d.get("content"), str):
            raise GitHubError("the README came in an encoding this tool doesn't read")
        raw = base64.b64decode(d["content"])
        if len(raw) > cap:
            raw = raw[:cap]
        return raw.decode("utf-8", "replace"), d

    def download(self, url, cap):
        """an asset's bytes, at most cap (TooBig past it)"""
        status, body = self._get(url, "application/octet-stream", cap)
        if status != 200:
            raise GitHubError(f"downloading {url}: GitHub answered {status}")
        return body
