"""Polite MediaWiki / Wikidata API client.

- Descriptive User-Agent with contact info (set FACTLE_CONTACT to an email to add it).
- Serial requests only, maxlag=5 on Wikipedia, exponential backoff on 429/5xx/maxlag, a minimum gap between calls.
- Responses for the batch lookups are cached on disk by the callers, so reruns hit the network rarely.
"""
import os
import time

import requests

CONTACT = os.environ.get("FACTLE_CONTACT", "https://github.com/biccyanzac-pixel/factle")
USER_AGENT = f"FactleBot/0.1 ({CONTACT}) python-requests/{requests.__version__}"
WP_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
MIN_GAP = 0.2  # seconds between requests

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
_last = 0.0


def call(api, params, tries=6, maxlag=True):
    global _last
    params = {"format": "json", "formatversion": "2", **({"maxlag": "5"} if maxlag else {}), **params}
    for attempt in range(tries):
        wait = MIN_GAP - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        try:
            r = _session.post(api, data=params, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(int(r.headers.get("Retry-After", 2 ** attempt)))
            continue
        r.raise_for_status()
        data = r.json()
        if data.get("error", {}).get("code") == "maxlag":
            time.sleep(int(r.headers.get("Retry-After", 5)))
            continue
        if "error" in data:
            raise RuntimeError(data["error"])
        return data
    raise RuntimeError(f"giving up on {api} {params.get('action')}")


def wp(params):
    return call(WP_API, params)


def wd(params):
    # Wikidata's maxlag includes query-service lag, which is aimed at bot edits and is often >5 s;
    # these are read-only requests, so they rely on serial pacing and backoff instead.
    return call(WD_API, params, maxlag=False)
