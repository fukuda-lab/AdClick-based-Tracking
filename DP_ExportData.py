"""
One database per (VP country, interaction): 6 countries x 3 interactions = 18 databases.
Keys
    id_site       : SERIAL, unique only within one database; never compared across databases.
    id_csv        : identifier of one AdURL, the same in all 18 databases; the notebook joins on (platform, id_csv).
    reached_etld1 : eTLD+1 of the final landing page; the notebook uses it as the advertiser.

Output ({country}_{case}_<name>.csv)
    sites_summary              1 row / visit: banner, AdClick-ID state, AdURL and landing URL
    clickid_flags              1 row / visit with a valid AdClick-ID: storage and tracking flags
    clickid_occ_storage        1 row / AdClick-ID found in a cookie, localStorage or sessionStorage entry
    clickid_occ_requests       1 row / (tracking request hop, channel) carrying the AdClick-ID; channels: uri, body, referer, cookie,
                               other_header, set_cookie, location, resp_header, resp_body
    auth_visit                 1 row / visit of Meta Ads, TikTok Ads, X Ads: authentication cookie of the platform and the AdClick-ID
                               in the same tracking request to the platform (cookie names only)
    clickid_params_upgrade     1 row / (tracking request, parameter) carrying the AdClick-ID after recursive URL / Base64 decoding,
                               with the SST-Guard label of first-party requests
    sst_visit_upgrade          1 row / (visit, host) with a server-side Google tag (SST-Guard) or a Google request
"""

import argparse
import ast
import base64
import binascii
import csv
import hashlib
import json
import math
import os
import re
import time
from urllib.parse import urlparse, urlsplit, parse_qsl, parse_qs, unquote, unquote_plus, quote

import psycopg2
import psycopg2.extras
import tldextract

from libs.dbProcess import get_db_conn
from libs.params import extract_TT_params_from_url

COUNTRIES = ["AU", "BR", "DE", "JP", "US", "ZA"]
CASES = ["no-interaction", "accept-all", "reject-all"]

# ====================================================================================================================
# Common
# ====================================================================================================================
CLICKID_PARAMS = {"FB": ["fbclid"], "GG": ["gclid"], "MS": ["msclkid"], "TW": ["twclid"], "TT": ["ttclid"], "YH": ["yclid"]}
PLATFORM_ENTITY = {"FB": "meta", "GG": "google", "MS": "microsoft", "TW": "twitter", "TT": "tiktok", "YH": "yahoo"}
# Domains of the six ad platforms. Used only to recognise the redirect chain of the AdURL (is_navigation) and Google hosts
# (served_by). The notebook maps recipients to organizations with Ghostery TrackerDB.
ENTITY_DOMAINS = {
    "google": ["google.com", "google-analytics.com", "googletagmanager.com", "doubleclick.net",
               "googleadservices.com", "googlesyndication.com", "gstatic.com", "youtube.com", "googleapis.com",
               "googletagservices.com", "app-measurement.com", "2mdn.net"],
    "meta": ["facebook.com", "facebook.net", "fbcdn.net", "instagram.com", "meta.com", "whatsapp.com", "fb.com", "messenger.com"],
    "microsoft": ["microsoft.com", "bing.com", "clarity.ms", "msn.com", "live.com", "linkedin.com", "licdn.com"],
    "tiktok": ["tiktok.com", "tiktokv.com", "tiktokcdn.com", "bytedance.com", "ttwstatic.com", "tiktokw.us", "byteoversea.com", "ibytedtos.com"],
    "twitter": ["twitter.com", "x.com", "t.co", "twimg.com", "ads-twitter.com", "twttr.com"],
    "yahoo": ["yahoo.co.jp", "yimg.jp"],          # Yahoo! JAPAN (LY Corp)
}
DOMAIN2ENTITY = {d: e for e, ds in ENTITY_DOMAINS.items() for d in ds}
GOOGLE_CC_RE = re.compile(r"^google\.(?:com?\.)?[a-z]{2,3}$")   # google.de, google.co.jp, google.com.au, ...

MIN_CLICKID_LEN = 10               # shorter values (including the empty string) are dropped
SEARCH_ENCODED_VARIANTS = True     # also match URL-encoded, Base64 and hashed forms
EXPORT_ONLY_TRACKERS = True        # clickid_occ_requests keeps tracking requests only (EasyList or EasyPrivacy)
SCAN_RESPONSE_BODY = True          # scan the full response body
BATCH_SITES = 200
FLUSH_EVERY = 500

HOST_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.\-]*://)?(?:[^/?#@]*@)?([^/:?#]+)")
_ext = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def entity_of(etld1):
    if not etld1:
        return "other"
    e = DOMAIN2ENTITY.get(etld1)
    if e:
        return e
    return "google" if GOOGLE_CC_RE.match(etld1) else "other"


def etld1_of(host):
    return (_ext(host).top_domain_under_public_suffix or host) if host else None


def host_of(url):
    m = HOST_RE.match(url) if isinstance(url, str) else None
    return m.group(1).lower() if m else None


def norm_url(u):
    return u.split("#")[0] if isinstance(u, str) else None


def dedupe_after_snapshot(rows, key_fields, tie_break_field=None):
    """The database stores the 'after' phase twice (right after the click and after the reload) without a flag.
    Keep is_after = False rows; merge is_after = True rows by key_fields and keep the row with the largest tie_break_field."""
    before = [r for r in rows if not r["is_after"]]
    best = {}
    for r in rows:
        if not r["is_after"]:
            continue
        key = tuple(r.get(f) for f in key_fields)
        if key not in best:
            best[key] = r
        elif tie_break_field and (r.get(tie_break_field) or -1) > (best[key].get(tie_break_field) or -1):
            best[key] = r
    return before + list(best.values())


# ---------------- AdClick-ID of the AdURL and of the landing URL ----------------
def multi_decode(url, max_rounds=5):
    previous = url
    for _ in range(max_rounds):
        decoded = unquote(previous)
        if decoded == previous:
            break
        previous = decoded
    return previous


def extract_GG_params_from_url(url):
    all_params = []
    parsed = urlparse(multi_decode(url or ""))
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        all_params.append({"name": k, "value": v})
    if ";" in parsed.path:
        for part in parsed.path.split(";")[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                all_params.append({"name": k, "value": v})
    return all_params


def decode_bing_target_info(bing_url):
    try:
        params = parse_qs(urlparse(bing_url).query)
        rlink = params.get("rlink", [None])[0]
        if not rlink:
            return None
        u = parse_qs(urlparse(rlink).query).get("u", [None])[0]
        if not u:
            return None
        decoded_url = unquote(base64.b64decode(u + "=" * (-len(u) % 4)).decode("utf-8"))
        parsed_target = urlparse(decoded_url)
        ext = tldextract.extract(parsed_target.hostname or "")
        return {"decoded_url": decoded_url,
                "msclkid": parse_qs(parsed_target.query).get("msclkid", [None])[0],
                "domain": ".".join(p for p in [ext.domain, ext.suffix] if p)}
    except Exception:
        return None


def _params_named(params, name):
    return [p["value"] for p in params if p["name"].lower() == name]


def clean_tokens(vals):
    return [v for v in vals if isinstance(v, str) and len(v.strip()) >= MIN_CLICKID_LEN]


def get_click_id_ads_url(adURL, platform):
    out = []
    if platform in ("TT", "TW"):
        out = _params_named(extract_TT_params_from_url(adURL), "ttclid" if platform == "TT" else "twclid")
    elif platform == "GG":
        out = _params_named(extract_GG_params_from_url(adURL), "gclid")
    elif platform == "FB":
        ps = extract_GG_params_from_url(adURL)
        out = _params_named(ps, "fbclid")
        for u in _params_named(ps, "u"):
            out += _params_named(extract_GG_params_from_url(u), "fbclid")
    elif platform == "MS":
        result = decode_bing_target_info(adURL)
        if result and result.get("msclkid"):
            out.append(result["msclkid"])
    return clean_tokens(out)


def get_click_id_reached_url(reachedURL, platform):
    out = []
    if platform in ("TT", "TW"):
        out = _params_named(extract_TT_params_from_url(reachedURL), "ttclid" if platform == "TT" else "twclid")
    elif platform in ("GG", "FB", "MS"):
        out = _params_named(extract_GG_params_from_url(reachedURL), CLICKID_PARAMS[platform][0])
    elif platform == "YH":
        out = parse_qs(urlparse(reachedURL or "").query).get("yclid", [])[:1]
    return clean_tokens(out)


# ---------------- matching ----------------
def make_variants(tok):
    v = {"raw": tok}
    enc = quote(tok, safe="")
    if enc != tok:
        v["urlenc"] = enc
    if SEARCH_ENCODED_VARIANTS:
        b = tok.encode()
        for name, s in [("b64", base64.b64encode(b).decode().rstrip("=")),
                        ("b64url", base64.urlsafe_b64encode(b).decode().rstrip("=")),
                        ("md5", hashlib.md5(b).hexdigest()),
                        ("sha1", hashlib.sha1(b).hexdigest()),
                        ("sha256", hashlib.sha256(b).hexdigest())]:
            if s not in v.values():
                v[name] = s
    return v


def match_kind(text, variants):
    if not isinstance(text, str) or not text:
        return False, ""
    raw = variants["raw"]
    if raw in text:
        return True, ("exact" if text == raw else "embedded")
    for name, v in variants.items():
        if name != "raw" and v and v in text:
            return True, name
    return False, ""


def match_any(text, variants_by_tok):
    for tok, var in variants_by_tok.items():
        ok, mk = match_kind(text, var)
        if ok:
            return tok, mk
    return None, ""


def param_name_of(url, tok):
    q = urlsplit(url)
    for part in (q.query, q.fragment):
        for k, v in parse_qsl(part, keep_blank_values=True):
            if tok in v:
                return k.lower()
    return "(other)"


def parse_headers(text):
    """Headers TEXT -> {lower-case name: value}. Reads JSON dict/list, Python dict repr and 'Name: value' lines."""
    if not text:
        return {}
    obj = None
    for loader in (json.loads, ast.literal_eval):
        try:
            obj = loader(text)
            break
        except Exception:
            continue
    if isinstance(obj, dict):
        return {str(k).lower(): (v if isinstance(v, str) else json.dumps(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        out = {}
        for h in obj:
            if isinstance(h, dict) and "name" in h:
                k = str(h["name"]).lower()
                out[k] = (out[k] + "\n" if k in out else "") + str(h.get("value", ""))
        return out
    out = {}
    for line in str(text).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().lower()
            out[k] = (out[k] + "\n" if k in out else "") + v.strip()
    return out


def cookie_lifetime_days(c):
    """Remaining lifetime of a cookie in days = expires - capture time (cookies.created_at). Session cookies -> None.
    created_at has no time zone: run the export in the time zone of the database."""
    exp, ts = c.get("expires"), c.get("created_at")
    if c.get("session") or exp is None or exp <= 0 or ts is None:
        return None
    return round((float(exp) - ts.timestamp()) / 86400, 2)


def recipient_class(etld1, adv_etld1):
    return "first_party" if etld1 and etld1 == adv_etld1 else "third_party"


class CsvWriter:
    def __init__(self, path, fieldnames):
        self.path, self.fieldnames = path, fieldnames
        self._wrote_header = os.path.exists(path)

    def write_rows(self, rows):
        if not rows:
            return
        with open(self.path, "a" if self._wrote_header else "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.fieldnames, extrasaction="ignore")
            if not self._wrote_header:
                w.writeheader()
                self._wrote_header = True
            w.writerows(rows)


def new_writer(outdir, country, case, name, fields):
    p = os.path.join(outdir, f"{country}_{case}_{name}.csv")
    if os.path.exists(p):
        os.remove(p)              # never append to the output of a previous run
    return CsvWriter(p, fields)


def _group(cur, sql, args):
    cur.execute(sql, args)
    d = {}
    for r in cur:
        d.setdefault(r["id_site"], []).append(r)
    return d


SQL_SITES = """
    SELECT s.id_site, s.id_csv, s.platform, s.run_no, s.domain_url, s.reached_url, s.crawl_status,
           (cb.id_site IS NOT NULL) AS banner_found, cb.user_choice, cb.cmp_name
    FROM sites s
    LEFT JOIN (
        SELECT DISTINCT ON (id_site) id_site, user_choice, cmp_name
        FROM consent_banners ORDER BY id_site, consent_id
    ) cb ON cb.id_site = s.id_site
    WHERE s.crawl_status = 'success' AND s.id_csv < 1090
    ORDER BY s.id_site
"""
SQL_COOKIES = """SELECT id_site, name, value, domain, path, expires, session, is_http_only, is_secure, same_site, is_after, created_at
                 FROM cookies WHERE id_site = ANY(%s)"""


def load_sites(conn, case, platforms=None):
    """Visits of the database; under accept all and reject all only visits with a banner."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(SQL_SITES)
        sites = cur.fetchall()
    return [s for s in sites if (case == "no-interaction" or s["banner_found"]) and (platforms is None or s["platform"] in platforms)]


# ====================================================================================================================
# Part 1 (main): sites_summary, clickid_flags, clickid_occ_storage, clickid_occ_requests
# ====================================================================================================================
# tracking requests (analysis) and Document requests (to recognise the redirect chain of the AdURL)
_TRK_FILTER = "AND (easylist OR privacylist OR resource_type = 'Document')" if EXPORT_ONLY_TRACKERS else ""
SQL_REQ = f"""
    SELECT request_id, id_site, request_url, method, resource_type, headers, post_data,
           is_third_party, easylist, privacylist, is_after, cdp_request_id
    FROM network_requests WHERE id_site = ANY(%s) {_TRK_FILTER}
    ORDER BY id_site, request_id
"""
# extra info and responses have no list flag -> keep only the cdp_request_id of tracking requests
_EXISTS_TRK = """AND EXISTS (SELECT 1 FROM network_requests r WHERE r.id_site = x.id_site
                 AND r.cdp_request_id = x.cdp_request_id AND (r.easylist OR r.privacylist))""" if EXPORT_ONLY_TRACKERS else ""
SQL_REQ_EXTRA = f"""
    SELECT x.id, x.id_site, x.cdp_request_id, x.headers, x.cookies
    FROM network_request_extra_info x WHERE x.id_site = ANY(%s) {_EXISTS_TRK} ORDER BY x.id_site, x.id
"""
SQL_RESP = f"""
    SELECT x.response_id AS id, x.id_site, x.cdp_request_id, x.response_url, x.status_code, x.headers, x.mime_type,
           x.is_after, {"x.response_body" if SCAN_RESPONSE_BODY else "NULL"} AS response_body
    FROM network_responses x WHERE x.id_site = ANY(%s) {_EXISTS_TRK} ORDER BY x.id_site, x.response_id
"""
SQL_RESP_EXTRA = f"""
    SELECT x.id, x.id_site, x.cdp_request_id, x.headers, x.cookies
    FROM network_response_extra_info x WHERE x.id_site = ANY(%s) {_EXISTS_TRK} ORDER BY x.id_site, x.id
"""
SQL_LOCAL = """SELECT id_site, lstorage_key AS name, lstorage_value AS value, origin, current_domain, is_after
               FROM local_storage WHERE id_site = ANY(%s)"""
SQL_SESSION = """SELECT id_site, sstorage_key AS name, sstorage_value AS value, origin, current_domain, is_after
                 FROM session_storage WHERE id_site = ANY(%s)"""

FIELDS = {
    "sites": ["vid", "country", "case", "platform", "id_csv", "run_no", "id_site", "crawl_status", "banner_found",
              "user_choice", "cmp_name", "clickid_state", "n_tokens",
              "domain_url", "adurl_host", "adurl_etld1", "reached_url", "reached_host", "reached_etld1"],
    "cid": ["vid", "country", "case", "platform", "id_csv", "run_no", "reached_etld1", "clickid_state",
            "stored", "stored_cookie",
            "trk_any", "trk_any_before", "trk_any_after",
            "trk_sent", "trk_sent_before", "trk_sent_after",
            "trk_sent_1p", "trk_sent_3p", "trk_sent_owner", "trk_sent_3p_nonowner",
            "trk_referer", "trk_cookie", "trk_set_cookie", "trk_set_cookie_1p", "trk_resp",
            "n_trk_req_with_cid", "n_trk_recipients", "n_trk_entities"],
    "occ_sto": ["vid", "country", "case", "platform", "id_csv", "storage_type", "domain", "name", "match_type",
                "expires", "session", "http_only", "is_after", "is_first_party", "lifetime_days"],
    "occ_req": ["vid", "country", "case", "platform", "id_csv", "run_no", "reached_etld1", "source", "request_id",
                "align", "method", "resource_type", "status_code", "channel", "param_key", "header_name",
                "match_type", "host", "etld1", "entity", "is_platform_owner", "recipient_class", "is_third_party", "easylist", "privacylist",
                "is_tracker", "is_after", "is_navigation"],
}
MAIN_NAMES = {"sites": "sites_summary", "cid": "clickid_flags", "occ_sto": "clickid_occ_storage", "occ_req": "clickid_occ_requests"}


def _align(rows_by_cdp, extras):
    """Attach each extra-info row to one request hop with the same cdp_request_id. Redirects share the cdp_request_id and CDP sends one
    ExtraInfo per hop in order: pair them in order if the counts match ('order'), otherwise attach to the last hop ('last');
    no request -> None ('orphan')."""
    by = {}
    for e in extras:
        by.setdefault(e["cdp_request_id"], []).append(e)
    out = []
    for cdp, es in by.items():
        hops = rows_by_cdp.get(cdp, [])
        if not hops:
            out += [(e, None, "orphan") for e in es]
        elif len(hops) == len(es):
            out += [(e, h, "order") for e, h in zip(es, hops)]
        else:
            out += [(e, hops[-1], "last") for e in es]
    return out


def _align_responses(rows_by_cdp, resps):
    out = []
    for e in resps:
        hops = rows_by_cdp.get(e["cdp_request_id"], [])
        same = [h for h in hops if norm_url(h["request_url"]) == norm_url(e["response_url"])]
        if same:
            out.append((e, same[-1], "url"))
        elif hops:
            out.append((e, hops[-1], "last"))
        else:
            out.append((e, None, "orphan"))
    return out


def scan_network(ctx, reqs, req_extra, resps, resp_extra, variants_by_tok):
    """Occurrences of the AdClick-ID in requests and responses of one visit."""
    owner = PLATFORM_ENTITY.get(ctx["platform"])
    landing = {norm_url(ctx["domain_url"]), norm_url(ctx["reached_url"])}

    # redirect chain of the AdURL (always carries the AdClick-ID in the URL) -> is_navigation, not counted as sent
    nav_cdp = set()
    for r in reqs:
        if r["resource_type"] == "Document":
            e1 = etld1_of(host_of(r["request_url"]))
            in_url = match_any(r["request_url"] or "", variants_by_tok)[0] is not None
            if norm_url(r["request_url"]) in landing or (in_url and entity_of(e1) == owner):
                nav_cdp.add(r["cdp_request_id"])

    rows_by_cdp = {}
    for r in reqs:
        rows_by_cdp.setdefault(r["cdp_request_id"], []).append(r)

    def hop_meta(h):
        if h is None:
            return {"request_id": None, "cdp_request_id": None, "is_tracker": False, "is_nav": False, "host": None, "is_after": None,
                    "method": None, "resource_type": None, "is_third_party": None, "easylist": None, "privacylist": None}
        return {"request_id": h["request_id"], "cdp_request_id": h["cdp_request_id"], "is_tracker": bool(h["easylist"]) or bool(h["privacylist"]),
                "is_nav": h["resource_type"] == "Document" and h["cdp_request_id"] in nav_cdp,
                "host": host_of(h["request_url"]), "is_after": h["is_after"], "method": h["method"],
                "resource_type": h["resource_type"], "is_third_party": h["is_third_party"],
                "easylist": h["easylist"], "privacylist": h["privacylist"]}

    occ, seen = [], set()

    def add(source, meta, align, channel, text, header_name="", status=None, url_for_key=None):
        tok, mk = match_any(text, variants_by_tok)
        if tok is None:
            return
        key = (meta["request_id"], source.split("_")[0], channel)   # one row per (hop, direction, channel)
        if meta["request_id"] is not None and key in seen:
            return
        seen.add(key)
        e1 = etld1_of(meta["host"])
        entity = entity_of(e1)
        occ.append({
            "source": source, "request_id": meta["request_id"], "cdp_request_id": meta["cdp_request_id"], "align": align, "method": meta["method"],
            "resource_type": meta["resource_type"], "status_code": status, "channel": channel,
            "param_key": param_name_of(url_for_key, tok) if (url_for_key and mk in ("exact", "embedded")) else "",
            "header_name": header_name, "match_type": mk, "host": meta["host"], "etld1": e1, "entity": entity,
            "recipient_class": recipient_class(e1, ctx["adv_etld1"]), "is_platform_owner": entity == owner,
            "is_third_party": meta["is_third_party"], "easylist": meta["easylist"], "privacylist": meta["privacylist"],
            "is_tracker": meta["is_tracker"], "is_after": meta["is_after"], "_nav": meta["is_nav"],
        })

    def scan_req_headers(source, meta, align, hdrs, cookies_text=None):
        for name, val in hdrs.items():
            if name == "referer":
                add(source, meta, align, "referer", val, name)
            elif name == "cookie":
                add(source, meta, align, "cookie", val, name)
            elif not name.startswith(":"):
                add(source, meta, align, "other_header", val, name)
        if cookies_text:
            add(source, meta, align, "cookie", cookies_text, "cookies(extra)")

    def scan_resp_headers(source, meta, align, hdrs, status, cookies_text=None):
        for name, val in hdrs.items():
            if name == "set-cookie":
                add(source, meta, align, "set_cookie", val, name, status)
            elif name == "location":
                add(source, meta, align, "location", val, name, status)
            elif not name.startswith(":"):
                add(source, meta, align, "resp_header", val, name, status)
        if cookies_text:
            add(source, meta, align, "set_cookie", cookies_text, "cookies(extra)", status)

    # 1) network_requests: URL, body, headers
    for r in reqs:
        meta = hop_meta(r)
        if EXPORT_ONLY_TRACKERS and not meta["is_tracker"]:
            continue
        add("request", meta, "self", "uri", r["request_url"] or "", url_for_key=r["request_url"])
        add("request", meta, "self", "body", r["post_data"] or "")
        scan_req_headers("request", meta, "self", parse_headers(r["headers"]))
    # 2) network_request_extra_info: full headers (including Cookie) and associated cookies
    for e, h, al in _align(rows_by_cdp, req_extra):
        meta = hop_meta(h)
        if EXPORT_ONLY_TRACKERS and not meta["is_tracker"]:
            continue
        scan_req_headers("request_extra", meta, al, parse_headers(e["headers"]), e.get("cookies"))
    # 3) network_responses: headers (Set-Cookie, Location) and body
    for e, h, al in _align_responses(rows_by_cdp, resps):
        meta = hop_meta(h)
        if EXPORT_ONLY_TRACKERS and not meta["is_tracker"]:
            continue
        if meta["is_after"] is None:
            meta["is_after"] = e.get("is_after")
        scan_resp_headers("response", meta, al, parse_headers(e["headers"]), e.get("status_code"))
        if e.get("response_body"):
            add("response", meta, al, "resp_body", e["response_body"], status=e.get("status_code"))
    # 4) network_response_extra_info: raw Set-Cookie and associated cookies
    for e, h, al in _align(rows_by_cdp, resp_extra):
        meta = hop_meta(h)
        if EXPORT_ONLY_TRACKERS and not meta["is_tracker"]:
            continue
        scan_resp_headers("response_extra", meta, al, parse_headers(e["headers"]), None, e.get("cookies"))
    return occ


def summarize_network(occ):
    """Visit flags from the occurrences (tracking requests, redirect chain excluded)."""
    o = [x for x in occ if x["is_tracker"] and not x["_nav"]]
    sent = [x for x in o if x["channel"] in ("uri", "body")]
    sc = [x for x in o if x["channel"] == "set_cookie"]
    return {
        "trk_any": bool(o),
        "trk_any_before": any(x["is_after"] is False for x in o),
        "trk_any_after": any(x["is_after"] is True for x in o),
        "trk_sent": bool(sent),
        "trk_sent_before": any(x["is_after"] is False for x in sent),
        "trk_sent_after": any(x["is_after"] is True for x in sent),
        "trk_sent_1p": any(x["recipient_class"] == "first_party" for x in sent),
        "trk_sent_3p": any(x["recipient_class"] == "third_party" for x in sent),
        "trk_sent_owner": any(x["is_platform_owner"] for x in sent),
        "trk_sent_3p_nonowner": any(x["recipient_class"] == "third_party" and not x["is_platform_owner"] for x in sent),
        "trk_referer": any(x["channel"] == "referer" for x in o),
        "trk_cookie": any(x["channel"] == "cookie" for x in o),
        "trk_set_cookie": bool(sc),
        "trk_set_cookie_1p": any(x["recipient_class"] == "first_party" for x in sc),
        "trk_resp": any(x["channel"] in ("resp_body", "resp_header", "location") for x in o),
        "n_trk_req_with_cid": len({x["request_id"] for x in o if x["request_id"] is not None}),
        "n_trk_recipients": len({x["etld1"] for x in sent if x["etld1"]}),
        "n_trk_entities": len({(x["entity"] if x["entity"] != "other" else x["etld1"]) for x in sent if x["etld1"]}),
    }


def process_site(s, country, case, reqs, req_extra, resps, resp_extra, cks, lst, sst):
    sid, id_csv, plat = s["id_site"], s["id_csv"], s["platform"]
    vid = f"{case}|{country}|{sid}"
    adurl_host, reached_host = host_of(s["domain_url"]), host_of(s["reached_url"])
    adv_etld1 = etld1_of(reached_host)
    base = {"vid": vid, "country": country, "case": case, "platform": plat, "id_csv": id_csv,
            "run_no": s["run_no"], "id_site": sid, "reached_etld1": adv_etld1}
    out = {k: [] for k in MAIN_NAMES}

    cks = dedupe_after_snapshot(cks, key_fields=("domain", "name", "path"), tie_break_field="expires")
    lst = dedupe_after_snapshot(lst, key_fields=("origin", "current_domain", "name"))
    sst = dedupe_after_snapshot(sst, key_fields=("origin", "current_domain", "name"))

    # ---- AdClick-ID of the AdURL (L) and of the landing URL (F) ----
    L = get_click_id_ads_url(s["domain_url"], plat)
    F = get_click_id_reached_url(s["reached_url"], plat)
    if not L and not F:
        state = "absent"
    elif L and not F:
        state = "dropped_after_redirect"
    elif F and not L:
        state = "added_after_redirect"
    elif set(L) == set(F):
        state = "same"
    else:
        state = "changed"
    tokens = sorted(set(L) | set(F))
    out["sites"].append({**base, "crawl_status": s["crawl_status"], "banner_found": s["banner_found"],
                         "user_choice": s["user_choice"], "cmp_name": s.get("cmp_name"), "clickid_state": state,
                         "n_tokens": len(tokens), "domain_url": s["domain_url"], "adurl_host": adurl_host,
                         "adurl_etld1": etld1_of(adurl_host), "reached_url": s["reached_url"],
                         "reached_host": reached_host})
    if not tokens:
        return out
    variants_by_tok = {t: make_variants(t) for t in tokens}

    # ---- storage ----
    stored = stored_cookie = False
    for c in cks:
        dom = c["domain"] or ""
        is_1p = etld1_of(dom.lstrip(".")) == adv_etld1
        tok, mk = match_any(c["value"] or "", variants_by_tok)
        if tok:
            stored = True
            stored_cookie = stored_cookie or is_1p
            out["occ_sto"].append({**base, "storage_type": "cookie", "domain": dom, "name": c["name"], "match_type": mk,
                                   "expires": c["expires"], "session": c["session"], "http_only": c["is_http_only"],
                                   "lifetime_days": cookie_lifetime_days(c), "is_after": c["is_after"], "is_first_party": is_1p})
    for stype, rows_ in (("localStorage", lst), ("sessionStorage", sst)):
        for c in rows_:
            tok, mk = match_any(c["value"] or "", variants_by_tok)
            if tok:
                stored = True
                out["occ_sto"].append({**base, "storage_type": stype, "domain": c["origin"] or c["current_domain"],
                                       "name": c["name"], "match_type": mk, "is_after": c["is_after"]})

    # ---- requests and responses ----
    ctx = {"platform": plat, "domain_url": s["domain_url"], "reached_url": s["reached_url"], "adv_etld1": adv_etld1}
    occ = scan_network(ctx, reqs, req_extra, resps, resp_extra, variants_by_tok)
    out["occ_req"] += [{**base, **x, "is_navigation": x["_nav"]} for x in occ if x["is_tracker"] or not EXPORT_ONLY_TRACKERS]
    out["cid"].append({**base, "clickid_state": state, "stored": stored, "stored_cookie": stored_cookie, **summarize_network(occ)})
    return out


def run_main(conn, country, case, outdir):
    writers = {k: new_writer(outdir, country, case, n, FIELDS[k]) for k, n in MAIN_NAMES.items()}
    sites = load_sites(conn, case)
    print(f"  [main] {len(sites)} visits")
    buf = {k: [] for k in writers}
    n_done = 0
    for i in range(0, len(sites), BATCH_SITES):
        batch = sites[i:i + BATCH_SITES]
        ids = [b["id_site"] for b in batch]
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            req_by = _group(cur, SQL_REQ, (ids,))
            rqx_by = _group(cur, SQL_REQ_EXTRA, (ids,))
            rsp_by = _group(cur, SQL_RESP, (ids,))
            rsx_by = _group(cur, SQL_RESP_EXTRA, (ids,))
            ck_by = _group(cur, SQL_COOKIES, (ids,))
            ls_by = _group(cur, SQL_LOCAL, (ids,))
            ss_by = _group(cur, SQL_SESSION, (ids,))
        for s in batch:
            sid = s["id_site"]
            res = process_site(s, country, case, req_by.get(sid, []), rqx_by.get(sid, []), rsp_by.get(sid, []),
                               rsx_by.get(sid, []), ck_by.get(sid, []), ls_by.get(sid, []), ss_by.get(sid, []))
            for k, rows in res.items():
                buf[k] += rows
            n_done += 1
        if n_done % FLUSH_EVERY < BATCH_SITES:
            for k, w in writers.items():
                w.write_rows(buf[k]); buf[k].clear()
            print(f"  [main] ... {n_done}/{len(sites)}")
    for k, w in writers.items():
        w.write_rows(buf[k])


# ====================================================================================================================
# Part 2 (auth): auth_visit — authentication cookie of the platform together with the AdClick-ID (Meta Ads, TikTok Ads, X Ads)
# ====================================================================================================================
# The crawler logs in again in every run, so cookie values change between runs: only cookie NAMES are used.
# Tracking request = EasyList / EasyPrivacy; Ghostery TrackerDB decides whether the request goes to the platform itself.
LOGIN_PLATFORMS = ["FB", "TT", "TW"]
PLATFORM_ORG = {"FB": "facebook", "TT": "bytedance_inc", "TW": "twitter"}          # organization_id in TrackerDB
AUTH_COOKIES = {
    "FB": ["c_user", "xs"],
    "TT": ["sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt", "uid_tt_ss", "sid_ucp_v1", "ssid_ucp_v1"],
    "TW": ["auth_token", "twid"],
}
AUTH_BATCH_SITES = 100
FIELDS_AUTH = ["vid", "country", "case", "platform", "id_csv", "run_no", "id_site", "reached_etld1",
               "auth_in_jar", "auth_in_jar_names", "auth_same_site", "auth_jar_domains", "auth_set_in_visit",
               "n_owner_req", "n_owner_req_extra", "n_owner_req_id",
               "auth_sent_any", "id_with_auth", "id_with_auth_before", "id_with_auth_after", "id_without_auth",
               "auth_blocked_on_id", "auth_block_reasons", "id_auth_hosts", "id_noauth_hosts"]

_E1 = lambda d: ".".join(d.split(".")[-3:]) if re.search(r"\.(co|com|ne|or|ac|go)\.[a-z]{2}$", d) else ".".join(d.split(".")[-2:])
TDB_ETLD1 = {}


def load_trackerdb(path):
    """domain -> organization_id; plus eTLD+1 -> organization when the eTLD+1 belongs to a single organization (as in the notebook)."""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    tdb = {r["domain"].lower(): r["organization_id"] for r in rows}
    by = {}
    for d, o in tdb.items():
        by.setdefault(_E1(d), set()).add(o)
    TDB_ETLD1.clear(); TDB_ETLD1.update({e: next(iter(o)) for e, o in by.items() if len(o) == 1})
    return tdb


def org_of(host, tdb):
    h = str(host or "").lower().strip(".")
    parts = h.split(".")
    for i in range(len(parts) - 1):
        o = tdb.get(".".join(parts[i:]))
        if o:
            return o
    return TDB_ETLD1.get(_E1(h)) if h else None


def _load(text):
    if text is None or text == "":
        return None
    if isinstance(text, (list, dict)):
        return text
    for f in (json.loads, ast.literal_eval):
        try:
            return f(text)
        except Exception:
            continue
    return None


def cookie_header_names(val):
    return {p.split("=", 1)[0].strip() for p in str(val or "").replace("\n", ";").split(";") if "=" in p}


def associated(cookies_text, blocked_text):
    """CDP associatedCookies -> (names sent, {name: [block reasons]})."""
    cs, br = _load(cookies_text), _load(blocked_text)
    ok, blocked = set(), {}
    if not isinstance(cs, list):
        cs = []
    aligned = isinstance(br, list) and len(br) == len(cs) and all(not isinstance(b, dict) for b in br)
    by_name = {}
    if isinstance(br, dict):
        by_name = {k: v for k, v in br.items()}
    elif isinstance(br, list) and not aligned:
        for b in br:
            if isinstance(b, dict):
                nm = b.get("name") or (b.get("cookie") or {}).get("name")
                rs = b.get("blockedReasons") or b.get("reasons") or b.get("blocked_reasons") or []
                if nm:
                    by_name.setdefault(nm, []).extend(rs if isinstance(rs, list) else [rs])
    for i, it in enumerate(cs):
        if not isinstance(it, dict):
            continue
        c = it.get("cookie") if isinstance(it.get("cookie"), dict) else it
        nm = c.get("name")
        if not nm:
            continue
        rs = it.get("blockedReasons") or []
        if aligned:
            rs = br[i] or []
        rs = rs if isinstance(rs, list) else [rs]
        rs += [r for r in (by_name.get(nm) or []) if r not in rs] if not isinstance(by_name.get(nm), str) else [by_name[nm]]
        rs = [r for r in rs if r]
        if rs:
            blocked.setdefault(nm, set()).update(map(str, rs))
        else:
            ok.add(nm)
    return ok, blocked


def set_cookie_names(val):
    """Set-Cookie lines -> {name: SameSite or 'unspecified'}."""
    out = {}
    for line in str(val or "").split("\n"):
        if "=" not in line:
            continue
        nm = line.split("=", 1)[0].strip()
        m = re.search(r";\s*samesite=([a-z]+)", line, re.I)
        out[nm] = m.group(1).capitalize() if m else "unspecified"
    return out


def auth_sql(owner_re):
    req = """SELECT request_id, id_site, request_url, method, resource_type, headers, post_data, is_after, cdp_request_id,
                    easylist, privacylist
             FROM network_requests WHERE id_site = ANY(%s)
               AND (resource_type = 'Document' OR ((easylist OR privacylist) AND request_url ~* %s))
             ORDER BY id_site, request_id"""
    ex = """AND EXISTS (SELECT 1 FROM network_requests r WHERE r.id_site = x.id_site AND r.cdp_request_id = x.cdp_request_id
            AND (r.easylist OR r.privacylist) AND r.request_url ~* %s)"""
    rqx = f"""SELECT x.id, x.id_site, x.cdp_request_id, x.headers, x.cookies, x.blocked_reasons
              FROM network_request_extra_info x WHERE x.id_site = ANY(%s) {ex} ORDER BY x.id_site, x.id"""
    rsx = f"""SELECT x.id, x.id_site, x.cdp_request_id, x.headers FROM network_response_extra_info x
              WHERE x.id_site = ANY(%s) {ex} ORDER BY x.id_site, x.id"""
    return req, rqx, rsx


def owner_regex(tdb):
    doms = sorted({d for d, o in tdb.items() if o in PLATFORM_ORG.values()})
    return r"^[a-z]+://([^/?#]*\.)?(" + "|".join(re.escape(d) for d in doms) + r")(:[0-9]+)?([/?#]|$)"


def process_auth_visit(s, country, case, reqs, rqx, rsx, cks, tdb):
    sid, plat = s["id_site"], s["platform"]
    org, auth = PLATFORM_ORG[plat], set(AUTH_COOKIES[plat])
    adv = etld1_of(host_of(s["reached_url"]))
    base = {"vid": f"{case}|{country}|{sid}", "country": country, "case": case, "platform": plat, "id_csv": s["id_csv"],
            "run_no": s["run_no"], "id_site": sid, "reached_etld1": adv}
    is_owner = lambda u: org_of(host_of(u), tdb) == org

    # (1) cookie jar: authentication cookies on the platform's domains
    jar = [c for c in cks if c["name"] in auth and org_of((c.get("domain") or "").lstrip("."), tdb) == org]
    ss = sorted({f"{c['name']}:{c.get('same_site') or 'NULL'}" for c in jar})
    # (1b) authentication cookies set again in the visit (Set-Cookie of responses from the platform)
    set_in = set()
    for e in rsx:
        for k, v in parse_headers(e["headers"]).items():
            if k == "set-cookie":
                set_in |= {f"{n}:{a}" for n, a in set_cookie_names(v).items() if n in auth}

    # (2) AdClick-ID and the redirect chain of the AdURL (as in part 1)
    cids = sorted(set(get_click_id_ads_url(s["domain_url"], plat)) | set(get_click_id_reached_url(s["reached_url"], plat)))
    cvar = {t: make_variants(t) for t in cids}
    landing = {norm_url(s["domain_url"]), norm_url(s["reached_url"])}
    by_cdp = {}
    for r in reqs:
        by_cdp.setdefault(r["cdp_request_id"], []).append(r)
    extra = {}
    for e, h, _ in _align(by_cdp, rqx):
        if h is not None:
            extra.setdefault(h["request_id"], []).append(e)

    f = dict(auth_sent_any=False, id_with_auth=False, id_with_auth_before=False, id_with_auth_after=False,
             id_without_auth=False, auth_blocked_on_id=False)
    reasons, h_auth, h_noauth, n_own, n_ext, n_id = set(), set(), set(), 0, 0, 0
    for r in reqs:
        url = r["request_url"] or ""
        if not (r.get("easylist") or r.get("privacylist")):
            continue                                                   # tracking requests only
        if not is_owner(url):
            continue                                                   # requests to the platform itself (TrackerDB)
        if r["resource_type"] == "Document" and (norm_url(url) in landing or (cids and match_any(url, cvar)[0])):
            continue                                                   # redirect chain of the AdURL
        n_own += 1
        ex = extra.get(r["request_id"], [])
        n_ext += bool(ex)
        hdr = parse_headers(r["headers"])
        sent = cookie_header_names(hdr.get("cookie"))
        blocked = {}
        ch = set()
        for e in ex:
            eh = parse_headers(e["headers"])
            sent |= cookie_header_names(eh.get("cookie"))
            ok, bl = associated(e.get("cookies"), e.get("blocked_reasons"))
            sent |= ok
            for k, v in bl.items():
                blocked.setdefault(k, set()).update(v)
            for k, v in eh.items():
                if cids and not k.startswith(":") and match_any(v, cvar)[0]:
                    ch.add({"referer": "referer", "cookie": "cookie"}.get(k, "header"))
        if cids:
            if match_any(url, cvar)[0]:
                ch.add("uri")
            if match_any(r["post_data"] or "", cvar)[0]:
                ch.add("body")
            for k, v in hdr.items():
                if not k.startswith(":") and match_any(v, cvar)[0]:
                    ch.add({"referer": "referer", "cookie": "cookie"}.get(k, "header"))
        a_sent = sorted(sent & auth)
        a_block = {k: v for k, v in blocked.items() if k in auth and k not in sent}
        f["auth_sent_any"] |= bool(a_sent)
        if not ch:
            continue
        n_id += 1
        host = host_of(url)
        if a_sent:
            f["id_with_auth"] = True
            f["id_with_auth_after" if r["is_after"] else "id_with_auth_before"] = True
            h_auth.add(host)
        else:
            f["id_without_auth"] = True
            h_noauth.add(host)
        if a_block:
            f["auth_blocked_on_id"] = True
            reasons |= {f"{k}:{x}" for k, v in a_block.items() for x in v}
    return {**base, "auth_in_jar": bool(jar), "auth_in_jar_names": "|".join(sorted({c["name"] for c in jar})), "auth_same_site": "|".join(ss),
            "auth_jar_domains": "|".join(sorted({(c.get("domain") or "") for c in jar})), "auth_set_in_visit": "|".join(sorted(set_in)),
            "n_owner_req": n_own, "n_owner_req_extra": n_ext, "n_owner_req_id": n_id, **f,
            "auth_block_reasons": "|".join(sorted(reasons)), "id_auth_hosts": "|".join(sorted(h_auth)[:10]),
            "id_noauth_hosts": "|".join(sorted(h_noauth)[:10])}


def run_auth(conn, country, case, outdir, tdb):
    rx = owner_regex(tdb)
    sql_req, sql_rqx, sql_rsx = auth_sql(rx)
    w = new_writer(outdir, country, case, "auth_visit", FIELDS_AUTH)
    sites = load_sites(conn, case, LOGIN_PLATFORMS)
    print(f"  [auth] {len(sites)} visits of Meta Ads, TikTok Ads, X Ads")
    for i in range(0, len(sites), AUTH_BATCH_SITES):
        batch = sites[i:i + AUTH_BATCH_SITES]; ids = [b["id_site"] for b in batch]
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rq = _group(cur, sql_req, (ids, rx)); x1 = _group(cur, sql_rqx, (ids, rx)); x2 = _group(cur, sql_rsx, (ids, rx))
            ck = _group(cur, SQL_COOKIES, (ids,))
        w.write_rows([process_auth_visit(s, country, case, rq.get(s["id_site"], []), x1.get(s["id_site"], []), x2.get(s["id_site"], []),
                                         ck.get(s["id_site"], []), tdb) for s in batch])


# ====================================================================================================================
# Part 3 (params): clickid_params_upgrade and sst_visit_upgrade
# ====================================================================================================================
# 3rd-party request: tracking <=> EasyList or EasyPrivacy.
# 1st-party request: labelled with the request-level classifier of SST-Guard (Jazlan et al., arXiv:2604.27497): 23 value-template regexes on
# the query values -> logistic regression, threshold 0.7. Regexes and coefficients are copied from the published extension
# (github.com/jazlan01/sst-guard), including the four quoted regexes (_eu, gcs, tcfd, ep.user_agent) that never match.
# Requests to google-analytics / doubleclick / googleads are skipped, as in the extension.
# SST_DECODE_OBFUSCATED: if a query value is Base64 of a URL or query string, decode it and classify again (sst_decoded = True);
# the notebook keeps only requests labelled on the plain query string.
PARAMS_BATCH_SITES = 200
MAX_DEPTH = 3
MAX_B64_CANDIDATES = 30
PATH_MAX = 120
SST_THRESHOLD = 0.7
SST_DECODE_OBFUSCATED = True
UAPV_REGEX = None                        # platformVersion of the crawling machine, if known; None = never matches

SST_FEATURES = [                         # order = feature order of the model
    ("cid", r"(?:GA\d+\.\d+\.)?\d{8,10}\.17\d{8,11}"),
    ("tid", r"G-[A-Z0-9]{10}"),
    ("dl", r"https://[^\s&#]+"),
    ("gtm", r"45[A-Za-z]{1,2}[0-9]{2}[A-Za-z0-9]+"),
    ("ul", r"([A-Za-z]{2}[-_][A-Za-z]{2})|([A-Za-z]{2})|([Ee]nglish)"),
    ("tag_exp", r"[0-9]{9}(~[0-9]{9}){8,}"),
    ("gcd", r"13([a-zA-Z_]{1}\d{1}){5}"),
    ("sid", r"\d{10}"),
    ("_p", r"\d{13}"),
    ("pscdl", r"(noapi|denied)"),
    ("tfd", r"\d{3,4}"),
    ("uaa", r"^(x86|arm)$"),
    ("uab", r"^(64|32)$"),
    ("uafvl", r'^(\[\{"brand":"[^"]+","version":"[^"]+"\}(,\{"brand":"[^"]+","version":"[^"]+"\})*\]|[A-Za-z0-9)(\s;|.%_-]+)$'),
    ("uap", r"^(Linux|macOS|Windows|Android|Chrome OS|Chromium OS|iOS)$"),
    ("uapv", UAPV_REGEX or r"(?!)"),
    ("en", r"(page_view|scroll|ad_impression|user_engagement|view_item_list|view_item|scroll_depth|view_promotion|scroll_75|time_engaged"
           r"|mp_pageview|ddm_standard_event|click|Scroll Depth|page_load_time|scroll_25|ads_impression|scroll_50|scroll_tracking|proctor"
           r"|Newsfeed_show|Playbook Fired|scroll_90|page_scroll)"),
    ("_gid", r"\d{8,10}.\d{9,10}"),
    ("_u", r"([A-Za-z]{17}|[A-Za-z]{14}|[A-Za-z]{9}|[A-Za-z]{16})~"),
    ("_eu", r"'([A-Za-z]{2,3}[A-Z]{4})|([A-Z]{2,4})|([A-Za-z]{2,3})'"),          # as published (quoted)
    ("gcs", r"'G[0-3\-]{3}'"),                                                   # as published (quoted)
    ("tcfd", r"'[0-6]{2}[0-9a-zA-Z]{2,3}[a-z]?$'"),                              # as published (quoted)
    ("ep.user_agent", r"'^([Mm]ozilla/\d+\.\d+\s+\([^)]+\)\s+.+)$'"),            # as published (quoted)
]
SST_RX = [(n, re.compile(rx)) for n, rx in SST_FEATURES]
# logistic regression (class 1) from models/logistic_regression_model.onnx; P = sigmoid(w·x + b)
SST_COEF = [2.1050854, 2.5246949, -0.2935981, 1.3862203, 0.4807868, 0.3422625, 1.0005281, 1.2613233, -0.9615015, 0.3305480,
            -1.9386688, 0.2582727, 0.2132839, 0.2816727, 0.1193253, 0.2051571, 1.1156709, 0.1867490, 1.9325210, -0.4847677,
            0.9401568, -1.2705652, 0.2412501]
SST_INTERCEPT = -2.2757227
SST_SKIP_HOST = re.compile(r"google-analytics|doubleclick|googleads|(^|\.)analytics\.google\.com$")
B64_RE = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")


def sst_features(query_values):
    return [int(any(rx.search(v) for v in query_values)) for _, rx in SST_RX]


def sst_prob(x):
    z = SST_INTERCEPT + sum(w * xi for w, xi in zip(SST_COEF, x))
    return 1.0 / (1.0 + math.exp(-z))


def _b64_text(s):
    for dec in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            t = dec(s + "=" * (-len(s) % 4)).decode("utf-8", errors="ignore")
        except (binascii.Error, ValueError):
            continue
        if len(t) >= 8 and sum(ch.isprintable() for ch in t) / len(t) > .85:
            return t
    return None


def sst_classify(url, host):
    """-> (prob, flag, decoded, feature bits, decoded text). Query string only, as in the extension."""
    if host and SST_SKIP_HOST.search(host):
        return 0.0, False, False, "", ""
    vals = [v for _, v in parse_qsl(urlsplit(url).query, keep_blank_values=True) if v != ""]
    x = sst_features(vals); p = sst_prob(x)
    if p >= SST_THRESHOLD or not SST_DECODE_OBFUSCATED:
        return p, p >= SST_THRESHOLD, False, "".join(map(str, x)), ""
    best = (p, x, "")
    for v in vals:
        for m in B64_RE.finditer(v):
            t = _b64_text(m.group(0))
            if not t or ("=" not in t):
                continue
            q = urlsplit(t).query if "?" in t else t
            vals2 = [v2 for _, v2 in parse_qsl(q, keep_blank_values=True) if v2 != ""]
            if vals2:
                x2 = sst_features(vals2); p2 = sst_prob(x2)
                if p2 > best[0]:
                    best = (p2, x2, t)
    dec = best[0] > p
    return best[0], best[0] >= SST_THRESHOLD, dec and best[0] >= SST_THRESHOLD, "".join(map(str, best[1])), best[2]


# Google tag signatures (columns google_tag, tag_id, gtag_rule, gtag_strong, tracking_class)
TID_RE = re.compile(r"^(G|UA|AW|DC|GT|GTM)-[A-Z0-9-]+$", re.I)
GTAG_PATHS = [
    ("GA4", re.compile(r"/g/(?:s/)?collect$")),
    ("Google Ads", re.compile(r"/pagead/(?:1p-)?(?:conversion|viewthroughconversion|landing|1p-user-list)|/ccm/(?:collect|form-data)|/rmkt/collect")),
    ("Floodlight", re.compile(r"/activityi?;|/ddm/(?:activity|fls)")),
    ("Tag loader", re.compile(r"/gtm\.js$|/gtag/js$")),
]


def google_tag_of(path, params):
    tid = next((v for k, v in params if k.lower() in ("tid", "id") and TID_RE.match(v or "")), "")
    ga4_v2 = any(k == "v" and v == "2" for k, v in params)
    for fam, rx in GTAG_PATHS:
        if rx.search(path or ""):
            strong = bool(tid) or (fam == "GA4" and ga4_v2) or fam == "Floodlight"
            return fam, tid, "path+id" if strong else "path"
    if tid:
        pre = tid.split("-")[0].upper()
        return {"G": "GA4", "UA": "Universal Analytics", "AW": "Google Ads", "DC": "Floodlight"}.get(pre, "Tag loader"), tid, "id"
    return "", "", ""


def gtag_strong(fam, rule):
    return bool(fam) and fam != "Tag loader" and (rule == "path+id" or (rule == "path" and fam in ("Google Ads", "Floodlight")))


def served_by(etld1, adv_etld1):
    if etld1 and adv_etld1 and etld1 == adv_etld1:
        return "first_party"
    return "google" if entity_of(etld1) == "google" else "other"


def _flatten_json(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten_json(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten_json(v, f"{prefix}[{i}]" if prefix else f"[{i}]")
    elif obj is not None:
        yield prefix or "(value)", str(obj)


def iter_params(url, body):
    sp = urlsplit(url or "")
    for k, v in parse_qsl(sp.query, keep_blank_values=True):
        yield "query", k, v
    if ";" in sp.path:
        for part in sp.path.split(";")[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                yield "path", k, v
    if body:
        try:
            for k, v in _flatten_json(json.loads(body)):
                yield "body", k, v
            return
        except Exception:
            pass
        found = False
        for line in str(body).splitlines():
            for k, v in (parse_qsl(line, keep_blank_values=True) if "=" in line else []):
                found = True
                yield "body", k, v
        if not found:
            yield "body", "(raw)", str(body)


def _b64_candidates(text):
    out = []
    for m in B64_RE.finditer(text):
        t = _b64_text(m.group(0))
        if t:
            out.append(t)
        if len(out) >= MAX_B64_CANDIDATES:
            break
    return out


def hashes_of(tok):
    b = tok.encode(); out = {}
    for name, fn in (("md5", hashlib.md5), ("sha1", hashlib.sha1), ("sha256", hashlib.sha256)):
        d = fn(b); out[name] = (d.hexdigest(), base64.b64encode(d.digest()).decode().rstrip("="))
    return out


def find_encoding(value, tokens, hashes):
    """-> (token, encoding chain) or (None, ''). Chains: plain, url, b64, url>b64, b64>url, hash:sha256, ..."""
    if not value:
        return None, ""
    frontier, seen = [("", value)], set()
    for depth in range(MAX_DEPTH + 1):
        nxt = []
        for chain, text in frontier:
            if text in seen:
                continue
            seen.add(text)
            for tok in tokens:
                if tok in text:
                    return tok, chain or "plain"
            if depth == MAX_DEPTH:
                continue
            u = unquote_plus(text)
            if u != text:
                nxt.append(((chain + ">" if chain else "") + "url", u))
            for t in _b64_candidates(text):
                nxt.append(((chain + ">" if chain else "") + "b64", t))
        frontier = nxt
        if not frontier:
            break
    low = value.lower()
    for tok in tokens:
        for name, (hx, b64d) in hashes[tok].items():
            if hx in low or b64d in value:
                return tok, f"hash:{name}"
    return None, ""


def mask(s, tokens):
    for t in tokens:
        s = s.replace(t, "<CID>")
    return s[:PATH_MAX]


# 3rd-party: listed requests only; 1st-party: every request with a query string (for SST-Guard) and every listed request
SQL_REQ_PARAMS = """
    SELECT request_id, id_site, request_url, method, resource_type, post_data, easylist, privacylist, is_third_party, is_after
    FROM network_requests
    WHERE id_site = ANY(%s)
      AND (easylist OR privacylist OR ((is_third_party IS NOT TRUE) AND strpos(request_url, '?') > 0))
    ORDER BY id_site, request_id
"""
FIELDS_OCC = ["vid", "country", "case", "platform", "id_csv", "run_no", "reached_etld1", "request_id", "is_after", "method",
              "resource_type", "host", "etld1", "entity", "recipient_class", "easylist", "privacylist", "is_tracker",
              "sst_prob", "sst_flag", "sst_decoded", "sst_features", "gtag_strong", "tracking_class", "is_navigation", "path",
              "google_tag", "tag_id", "gtag_rule", "served_by", "location", "param_key", "encoding", "value_len"]
FIELDS_SST = ["vid", "country", "case", "platform", "id_csv", "run_no", "host", "served_by", "n_sst_requests", "n_gtag_only_requests",
              "n_gtag_only_ga4", "n_sst_and_gtag", "n_sst_listed", "n_gtag_only_listed", "n_sst_decoded", "n_google_requests",
              "n_with_clickid", "max_sst_prob", "families", "paths"]


def process_site_params(s, country, case, reqs):
    sid, plat = s["id_site"], s["platform"]
    adv = etld1_of(host_of(s["reached_url"]))
    tokens = sorted(set(get_click_id_ads_url(s["domain_url"], plat)) | set(get_click_id_reached_url(s["reached_url"], plat)))
    base = {"vid": f"{case}|{country}|{sid}", "country": country, "case": case, "platform": plat, "id_csv": s["id_csv"],
            "run_no": s["run_no"], "reached_etld1": adv}
    if not tokens:
        return [], []
    hashes = {t: hashes_of(t) for t in tokens}
    landing = {norm_url(s["domain_url"]), norm_url(s["reached_url"])}
    owner = PLATFORM_ENTITY.get(plat)
    occ, sstv = [], {}
    for r in reqs:
        url = r["request_url"] or ""
        host = host_of(url); e1 = etld1_of(host)
        rc = recipient_class(e1, adv)
        el, pl = bool(r["easylist"]), bool(r["privacylist"])
        listed = el or pl
        is_nav = r["resource_type"] == "Document" and (norm_url(url) in landing or (entity_of(e1) == owner and any(t in url for t in tokens)))
        if is_nav:
            continue
        if rc == "first_party":
            p, flag, dec, bits, dtext = sst_classify(url, host)
        else:
            p, flag, dec, bits, dtext = 0.0, False, False, "", ""
        if rc == "third_party" and not listed:
            continue
        sp = urlsplit(url)
        qparams = parse_qsl(sp.query, keep_blank_values=True)
        if ";" in sp.path:
            qparams += [tuple(x.split("=", 1)) for x in sp.path.split(";")[1:] if "=" in x]
        fam, tid, rule = google_tag_of(sp.path, qparams)
        if not fam and dec and dtext:                 # obfuscated server-side tag: family from the decoded URL
            dsp = urlsplit(dtext if dtext.startswith(("/", "http")) else "/?" + dtext)
            fam, tid, rule = google_tag_of(dsp.path, parse_qsl(dsp.query, keep_blank_values=True))
        strong = gtag_strong(fam, rule)
        if rc == "third_party":
            tclass = "3P-listed"
        else:
            if flag:
                tclass = "1P-SST"
            elif strong:
                tclass = "1P-GTAG"
            elif listed:
                tclass = "1P-listed"
            else:
                continue
            if listed and tclass != "1P-listed":
                tclass += "+listed"
        params = list(iter_params(url, r["post_data"]))
        hit = False
        for loc, k, v in params:
            tok, enc = find_encoding(v, tokens, hashes)
            if not tok:
                continue
            hit = True
            occ.append({**base, "request_id": r["request_id"], "is_after": r["is_after"], "method": r["method"],
                        "resource_type": r["resource_type"], "host": host, "etld1": e1, "entity": entity_of(e1), "recipient_class": rc,
                        "easylist": el, "privacylist": pl, "is_tracker": listed, "sst_prob": round(p, 4), "sst_flag": flag,
                        "sst_decoded": dec, "sst_features": bits, "gtag_strong": strong, "tracking_class": tclass, "is_navigation": False,
                        "path": mask(sp.path, tokens), "google_tag": fam, "tag_id": tid, "gtag_rule": rule,
                        "served_by": served_by(e1, adv), "location": loc, "param_key": k[:80], "encoding": enc, "value_len": len(v)})
        g3 = rc == "third_party" and entity_of(e1) == "google"
        if (rc == "first_party" and (flag or strong)) or g3:
            d = sstv.setdefault(host, {"sb": "first_party" if rc == "first_party" else "google", "sst": 0, "gtag": 0, "ga4": 0, "both": 0,
                                       "sst_l": 0, "gtag_l": 0, "dec": 0, "g": 0, "cid": 0, "p": 0.0, "fams": set(), "paths": []})
            d["g"] += int(g3); d["cid"] += int(hit)
            if rc == "first_party":
                d["sst"] += int(flag); d["gtag"] += int(strong and not flag); d["both"] += int(flag and strong)
                d["ga4"] += int(strong and not flag and fam == "GA4")
                d["sst_l"] += int(flag and listed); d["gtag_l"] += int(strong and not flag and listed)
                d["dec"] += int(dec); d["p"] = max(d["p"], p)
            if fam:
                d["fams"].add(fam)
            pm = mask(sp.path, tokens)
            if pm not in d["paths"] and len(d["paths"]) < 5:
                d["paths"].append(pm)
    rows_v = [{**{k: base[k] for k in ("vid", "country", "case", "platform", "id_csv", "run_no")}, "host": h, "served_by": d["sb"],
               "n_sst_requests": d["sst"], "n_gtag_only_requests": d["gtag"], "n_gtag_only_ga4": d["ga4"], "n_sst_and_gtag": d["both"],
               "n_sst_listed": d["sst_l"], "n_gtag_only_listed": d["gtag_l"], "n_sst_decoded": d["dec"],
               "n_google_requests": d["g"], "n_with_clickid": d["cid"], "max_sst_prob": round(d["p"], 4), "families": ",".join(sorted(d["fams"])),
               "paths": " | ".join(d["paths"])} for h, d in sstv.items()]
    return occ, rows_v


def run_params(conn, country, case, outdir):
    w_occ = new_writer(outdir, country, case, "clickid_params_upgrade", FIELDS_OCC)
    w_sst = new_writer(outdir, country, case, "sst_visit_upgrade", FIELDS_SST)
    sites = load_sites(conn, case)
    print(f"  [params] {len(sites)} visits")
    for i in range(0, len(sites), PARAMS_BATCH_SITES):
        batch = sites[i:i + PARAMS_BATCH_SITES]
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            by = _group(cur, SQL_REQ_PARAMS, ([b["id_site"] for b in batch],))
        occ, sst = [], []
        for s in batch:
            o, v = process_site_params(s, country, case, by.get(s["id_site"], []))
            occ += o; sst += v
        w_occ.write_rows(occ); w_sst.write_rows(sst)


# ====================================================================================================================
def main(country, case, outdir, tdb):
    print(f"Start {country} / {case}")
    with get_db_conn(country, case) as conn:
        run_main(conn, country, case, outdir)
        run_auth(conn, country, case, outdir, tdb)
        run_params(conn, country, case, outdir)
    print(f"Done {country} / {case}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", choices=COUNTRIES)
    ap.add_argument("--case", choices=CASES)
    ap.add_argument("--out", default="ExportData")
    ap.add_argument("--trackerdb", default="trackerdb_domains.csv")
    a = ap.parse_args()
    
    os.makedirs(a.out, exist_ok=True)
    tdb = load_trackerdb(a.trackerdb)

    main(a.country, a.case, a.out, tdb)
