"""FarmMarket backend package.

Startup hygiene: some environments export NO_PROXY with bracketed IPv6
entries (e.g. "[::1]"). httpx cannot parse those and raises InvalidURL
before any request is made. Strip bracketed entries here so every module
importing this package gets a parseable NO_PROXY. Harmless elsewhere:
unbracketed entries are kept verbatim.
"""
import os

for _var in ("NO_PROXY", "no_proxy"):
    _val = os.environ.get(_var)
    if _val and ("[" in _val or "]" in _val):
        _kept = [p.strip() for p in _val.split(",") if p.strip() and "[" not in p and "]" not in p]
        os.environ[_var] = ",".join(_kept)
