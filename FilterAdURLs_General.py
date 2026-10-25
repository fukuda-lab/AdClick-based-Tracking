from pathlib import Path
from urllib.parse import urlparse, parse_qsl, unquote, parse_qs
import tldextract
import csv
import base64
import urllib.parse
import tldextract
from collections import defaultdict
import os
import pandas as pd
from libs.params import extract_TT_params_from_url
import random
import argparse

parser = argparse.ArgumentParser(description="Filter AdURLs")
parser.add_argument("--sampleRandom", required=True, type=int, help="Number of sites random/domain")
parser.add_argument("--round", required=True, type=int, help="Num of round")

args = parser.parse_args()
sampleRandom = args.sampleRandom
round = args.round

def readAdHoc(file):
    df = pd.read_csv(file)
    lstUrl_existing = df['ads_url'].to_list()
    return lstUrl_existing

def extract_FB_landing_url(facebook_url: str) -> str | None:
    parsed = urlparse(facebook_url)

    # Get the "u" query parameter
    params = parse_qs(parsed.query)
    target = params.get("u")

    if not target:
        return None

    target = target[0]

    # Decode repeatedly in case the URL is encoded multiple times
    for _ in range(5):
        decoded = unquote(target)
        if decoded == target:
            break
        target = decoded
    return target

def Filter_FB_AdURL(urls, ID_START, SAMPLE_RANDOM, urlsExisiting):
    domains = defaultdict(list)
    
    domainsExisting = set()
    for u in urlsExisiting:
        target_url = extract_FB_landing_url(u)
        if target_url:
            domain = extract_reached_domain(target_url)
            if domain:
                domainsExisting.add(domain)

    for u in urls:
        target_url = extract_FB_landing_url(u)
        if target_url:
            domain = extract_reached_domain(target_url)

            if domain and domain not in domainsExisting:
                domains[domain].append(u)
        #else:
        #    print(u)

    rows = []
    current_id = ID_START
    for domain, domain_urls in domains.items():
        domain_urls = list(set(domain_urls))
        selected = random.sample(domain_urls,min(SAMPLE_RANDOM,len(domain_urls)))

        for url in selected:
            rows.append({"id_site":current_id, "ads_url":url})
            current_id += 1
    return rows

def Filter_YH_AdURL(input_csv, ID_START, SAMPLE_RANDOM, input_csv_AdHoc):
    domainsExisting = set()
    domains = defaultdict(list)

    with open(input_csv_AdHoc,"r",encoding="utf-8-sig",newline="") as f:
        reader = csv.DictReader(f)
    
        for row in reader:
            domain = row.get("domain", "").strip()
            yclid = row.get("yclid", "").strip()
            if domain and yclid:
                domainsExisting.add(domain)


    with open(input_csv,"r",encoding="utf-8-sig",newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            src_url  = row.get("source_url", "").strip()
            dst_url = row.get("dest_url", "").strip()
            domain = row.get("domain", "").strip()
            yclid = row.get("yclid", "").strip()

            if domain and (domain not in domainsExisting) and yclid:
                domains[domain].append(src_url)

    rows = []
    current_id = ID_START
    for domain, domain_urls in domains.items():
        domain_urls = list(set(domain_urls))
        selected = random.sample(domain_urls, min(SAMPLE_RANDOM,len(domain_urls)))

        for url in selected:
            rows.append({"id_site": current_id, "ads_url": url})
            current_id += 1

    #Update AdHoc CSV
    with open(input_csv_AdHoc, mode='a', newline='', encoding='utf-8') as dest_file:
        writer = csv.writer(dest_file)
        with open(input_csv, mode='r', encoding='utf-8') as source_file:
            reader = csv.reader(source_file)
            next(reader) 
            writer.writerows(reader)
    
    return rows

def multi_decode(url, max_rounds=5):
    """
    Decode URL nhiều lần cho đến khi không đổi nữa
    """
    previous = url
    for _ in range(max_rounds):
        decoded = unquote(previous)
        if decoded == previous:
            break
        previous = decoded
    return previous



def extract_params_from_url(url):
    """
    Universal extractor:
    - Query parameters (?a=1&b=2)
    - Matrix parameters (;a=1;b=2)
    - Double/triple encoded URLs
    """

    all_params = []
    decoded_url = multi_decode(url)

    parsed = urlparse(decoded_url)
    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    for k, v in query_params:
        all_params.append({"name": k, "value": v})
    if ";" in parsed.path:
        parts = parsed.path.split(";")[1:]  # bỏ phần path đầu
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                all_params.append({"name": k, "value": v})

    return all_params


def extract_reached_domain(url):
    if not url:
        return ""
    try:
        ext = tldextract.extract(url)
        if not ext.domain or not ext.suffix:
            return ""
        return f"{ext.domain}.{ext.suffix}"
    except Exception as e:
        return ""



def decode_bing_target_info(bing_url: str):
    try:
        # Parse Bing URL
        parsed = urllib.parse.urlparse(bing_url)
        params = urllib.parse.parse_qs(parsed.query)

        rlink = params.get("rlink", [None])[0]
        if not rlink:
            return None

        # Parse rlink
        parsed_rlink = urllib.parse.urlparse(rlink)
        rlink_params = urllib.parse.parse_qs(parsed_rlink.query)

        u = rlink_params.get("u", [None])[0]
        if not u:
            return None

        # Base64 decode
        padding = "=" * (-len(u) % 4)
        decoded_url = urllib.parse.unquote(
            base64.b64decode(u + padding).decode("utf-8")
        )

        # Parse decoded url
        parsed_target = urllib.parse.urlparse(decoded_url)
        target_params = urllib.parse.parse_qs(parsed_target.query)

        msclkid = target_params.get("msclkid", [None])[0]

        ext = tldextract.extract(parsed_target.hostname or "")
        domain = ".".join(
            part for part in [ext.domain, ext.suffix] if part
        )

        return {
            "decoded_url": decoded_url,
            "msclkid": msclkid,
            "domain": domain,
        }

    except Exception:
        return None

def Filter_MS_AdURL(lst, ID_START, SAMPLE_RANDOM, urlsExisting):
    domainsExisting = set()
    domains = defaultdict(list)

    for ads_url in urlsExisting:
        result = decode_bing_target_info(ads_url)
        domain = result["domain"]
        domainsExisting.add(domain)

    for ads_url in lst:
        result = decode_bing_target_info(ads_url)
        domain = result["domain"]
        if domain and (domain not in domainsExisting) and (result['msclkid'] is not None):
            domains[domain].append(ads_url)

    rows = []
    current_id = ID_START

    for domain, domain_urls in domains.items():
        domain_urls = list(set(domain_urls))

        selected = random.sample(domain_urls, min(SAMPLE_RANDOM,(len(domain_urls))))

        for url in selected:
            rows.append({"id_site":current_id, "ads_url":url})
            current_id += 1
    return rows

def write_file(rows, output_file, output_Adhoc_file):
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f,fieldnames=["id_site", "ads_url"])
        writer.writeheader()
        writer.writerows(rows)

    with open(output_Adhoc_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f,fieldnames=["id_site", "ads_url"])
            writer.writerows(rows)

def Filter_TT_X_AdURL(lst, type, ID_START, SAMPLE_RANDOM, urlsExisting):
    domainsExisting = set()
    domains = defaultdict(list)
    for u in urlsExisting:
        domain = extract_reached_domain(u)
        domainsExisting.add(domain)

    for u in lst:
        is_contain_clickId = False
        domain = extract_reached_domain(u)
        params = extract_TT_params_from_url(u)

        for p in params:
            if p["name"].lower() == type:
                is_contain_clickId = True
                break
        
        if domain and (domain not in domainsExisting) and is_contain_clickId:
            domains[domain].append(u)
    
    rows = []
    current_id = ID_START

    for domain, domain_urls in domains.items():
        domain_urls = list(set(domain_urls))

        selected = random.sample(domain_urls, min(SAMPLE_RANDOM, len(domain_urls)))
        for url in selected:
            rows.append({"id_site": current_id, "ads_url": url})
            current_id += 1

    return rows


folder_path = Path("adURLs")

urlFB = set()
urlTW = set()
urlTT = set()

urlGG = set()
urlMS = set()
urlTotalGG = set()


# Loop through all files in the directory
for file in folder_path.iterdir():
    if file.is_file():
        fname = str(file.name)
        with open(file,"r", encoding="utf-8") as f:
            if fname.startswith("Twitter"):
                for line in f:
                    urlTW.add(line.strip())

            if fname.startswith("TiKTok"):
                for line in f:
                    urlTT.add(line.strip())

            if fname.startswith("Facebook"):
                for line in f:
                    urlFB.add(line.strip())

            if fname.startswith("MS"):
                for line in f:
                    urlMS.add(line.strip())

            if fname.startswith("TOTAL_GG"):
                for line in f:
                    urlTotalGG.add(line.strip())

#========= GOOGLE ========

SPECIAL_ADS_HOSTS = {
    "doubleclick.net",
    "googlesyndication.com",
}

DOMAINS_EXCLUDES = ("theguardian.com", "bbc.com")

INVALID_START_PREFIXES = (
    "chrome-error://",
    "about:blank",
    "https://account.microsoft.com/privacy/ad-settings",
    "https://adssettings.google.com/whythisad?source",
    "https://advanced-store.com/en/data-privacy/",
    "https://app.adroll.com/optout/privacysandbox",
    "https://popup.taboola.com/",
    "https://privacy.as.criteo.com/adchoices",
    "javascript:",
    "mailto:",
    "tel:",
    "https://www.spotify.com/legal",
    "https://www.spotify.com/legal/privacy-policy/",
    "whatsapp://"
    "https://s0.2mdn.net/",
    "https://privacy.us.criteo.com/adchoices",
    "https://privacy.eu.criteo.com/adchoices",
    "https://pixel.quantcount.com",
    "https://economictimes.indiatimes.com",
    "https://m.economictimes.com",
    "https://www.dianomi.com/whatsthis",
    "https://www.google.com/url?ct=abg&q=https://www.google.com/adsense/support/bin/request",
    "https://support.google.com",
    "https://support.apple.com",
    "https://support.mozilla.org",
    "https://support.microsoft.com",
    "https://optout.",
    "https://legal.yahoo.com",
    "https://www.youtube.com",
    "https://youtu.be/"
    "https://youradchoices.com",
    "https://www.facebook.com/",
    "https://facebook.com/"
    "https://www.x.com/",
    "https://x.com",
    "https://twitter.com/",
    "https://www.twitter.com/",
    "https://yahoo.com/",
    "https://www.yahoo.com/",
    "https://www.instagram.com/",
    "https://instagram.com/",
    "https://www.tiktok.com/@",
    "https://tiktok.com/@",
    "https://www.huffpost.com/",
    "https://www.whatsapp.com/",
    "https://whatsapp.com/",
    "https://www.snapchat.com/",
    "https://snapchat.com/",
    "https://www.linkedin.com/",
    "https://linkedin.com/",
    "https://api.whatsapp.com/",
    "https://cloud.google.com",
    "https://advertising.bbcstudios.com/",
    "https://www.theguardian.com",
    "https://www.google.com/preferences/",
    "https://google.com/preferences/"
)

INVALID_END_PREFIXES = (
    "/privacy/",
    "/analytics.html"
    "privacy"
)

EXLCUDES = (
    {"guardian.co.uk": "guardian.com"},
    {"dailymail.co.uk": "dailymail.com"},
    {"huffingtonpost.com": "huffpost.com"},
    {"thetimes.co.uk": "thetimes.com"},
    {"bbci.co.uk": "bbc.com"},
    {"wired.com": "wired.co.uk"}
)

# List domain of Google Ads
GOOGLE_AD_DOMAINS = [
    "googleadservices.com",
    "doubleclick.net",
    "googlesyndication.com",
]

SAFEFRAME_KEYWORDS = [
    "safeframe.googlesyndication.com",
    "/safeframe/",
]

def is_special_ads_host(host):
    if not host:
        return False
    return any(host.endswith(d) for d in SPECIAL_ADS_HOSTS)


def extract_ads_domain(url):
    if not url:
        return ""

    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()

        if not host:
            return ""
        if is_special_ads_host(host):
            return host
        ext = tldextract.extract(host)
        if not ext.domain or not ext.suffix:
            return host

        return f"{ext.domain}.{ext.suffix}"

    except Exception:
        return ""

def extract_reached_domain(url):
    if not url:
        return ""

    try:
        ext = tldextract.extract(url)
        if not ext.domain or not ext.suffix:
            return ""
        return f"{ext.domain}.{ext.suffix}"
    except Exception:
        return ""

def extract_domain(url):
    if not url:
        return ""

    try:
        ext = tldextract.extract(url)
        if not ext.domain or not ext.suffix:
            return ""
        return f"{ext.domain}"
    except Exception:
        return ""


def is_google_ads_domain(url: str) -> bool:
    try:
        hostname = urlparse(url).hostname or ""
        return any(
            hostname == d or hostname.endswith("." + d)
            for d in GOOGLE_AD_DOMAINS
        )
    except Exception:
        return False

    
    
def is_safeframe(url: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        path = parsed.path or ""
        return (
            "safeframe.googlesyndication.com" in hostname
            or "/safeframe/" in path
        )
    except Exception:
        return False

def is_valid_url(url: str) -> bool:
    if not url:
        return False

    url = url.strip().lower()
    if url.startswith(INVALID_START_PREFIXES) or url.endswith(INVALID_END_PREFIXES):
        return False
    else:
        return True

def Filter_GG_AdURL(urls, ID_START, SAMPLE_RANDOM, urlsExisting):
    domainsExisting = set()

    list_ads_url = set()
    list_non_gg_ads = set()
    list_gg_ads_gclid = set()
    domains_gg = defaultdict(list)

    for ads_url in urlsExisting:
        params = extract_params_from_url(ads_url)
        for p in params:
            if p["name"].lower() == "adurl":
                advertiser_domain = extract_reached_domain(p["value"])
                domainsExisting.add(advertiser_domain)
                break

    for ads_url in urls:                        
        if is_valid_url(ads_url):
            list_ads_url.add(ads_url)
            if is_safeframe(ads_url):
                continue

            if is_google_ads_domain(ads_url):
                has_gclid = False
                has_adurl = False
                advertiser_url = None
                                
                params = extract_params_from_url(ads_url)
                for p in params:
                    if p["name"].lower() == "gclid":
                        has_gclid = True
                        break
                                        
                                
                for p in params:
                    if p["name"].lower() == "adurl":
                        has_adurl = True
                        advertiser_url = p["value"]
                        break
                                
                if has_adurl and has_gclid:
                    list_gg_ads_gclid.add(ads_url)
                    #ads_domain = extract_ads_domain(ads_url)
                    advertiser_domain = extract_reached_domain(advertiser_url)
                    
                    if advertiser_domain not in domainsExisting:
                        #continue
                        #pair = (ads_domain,advertiser_domain)
                        domains_gg[advertiser_domain].append(ads_url)

                            
            else:
                list_non_gg_ads.add(ads_url)

    rows = []
    current_id = ID_START
    for advertiser_domain, domain_urls in domains_gg.items():
        domain_urls = list(set(domain_urls))

        selected = random.sample(domain_urls, min(SAMPLE_RANDOM, len(domain_urls)))
        for url in selected:
            rows.append({"id_site": current_id, "ads_url": url})
            current_id += 1

    return rows
#--------------
BASE_DIR_ADHOC = f"O_General_Filter_AdHoc"
BASE_DIR = f"O_General_Filter_{str(round)}"
os.makedirs(BASE_DIR, exist_ok=True)

ADHOC_MS_SELECTED_VISIT_ADS = f"{BASE_DIR_ADHOC}/O_MS_AdHoc_selected_adsURL.csv"
ADHOC_TT_SELECTED_VISIT_ADS = f"{BASE_DIR_ADHOC}/O_TT_AdHoc_selected_adsURL.csv"
ADHOC_TW_SELECTED_VISIT_ADS = f"{BASE_DIR_ADHOC}/O_TW_AdHoc_selected_adsURL.csv"
ADHOC_FB_SELECTED_VISIT_ADS = f"{BASE_DIR_ADHOC}/O_FB_AdHoc_selected_adsURL.csv"
ADHOC_YH_SELECTED_VISIT_ADS = f"{BASE_DIR_ADHOC}/O_YH_AdHoc_selected_adsURL.csv"
ADHOC_GG_SELECTED_VISIT_ADS = f"{BASE_DIR_ADHOC}/O_GG_AdHoc_selected_adsURL.csv"


urlMS_existing = readAdHoc(ADHOC_MS_SELECTED_VISIT_ADS)
urlTT_existing = readAdHoc(ADHOC_TT_SELECTED_VISIT_ADS)
urlTW_existing = readAdHoc(ADHOC_TW_SELECTED_VISIT_ADS)
urlFB_existing = readAdHoc(ADHOC_FB_SELECTED_VISIT_ADS)
urlYH_existing = readAdHoc(ADHOC_YH_SELECTED_VISIT_ADS)
urlGG_existing = readAdHoc(ADHOC_GG_SELECTED_VISIT_ADS)

MS_SELECTED_VISIT_ADS = f"{BASE_DIR}/O_MS_Round{str(round)}_selected_adsURL.csv"
TT_SELECTED_VISIT_ADS = f"{BASE_DIR}/O_TT_Round{str(round)}_selected_adsURL.csv"
TW_SELECTED_VISIT_ADS = f"{BASE_DIR}/O_TW_Round{str(round)}_selected_adsURL.csv"
FB_SELECTED_VISIT_ADS = f"{BASE_DIR}/O_FB_Round{str(round)}_selected_adsURL.csv"
YH_SELECTED_VISIT_ADS = f"{BASE_DIR}/O_YH_Round{str(round)}_selected_adsURL.csv"
GG_SELECTED_VISIT_ADS = f"{BASE_DIR}/O_GG_Round{str(round)}_selected_adsURL.csv"

if round == 1:
    start_ = 1
else:
    df = pd.read_csv(ADHOC_YH_SELECTED_VISIT_ADS)
    lastID = df.iloc[-1]['id_site']
    start_ = lastID + 1

FB_rows = Filter_FB_AdURL(urlFB, start_, sampleRandom, urlFB_existing)
start_ += len(FB_rows)

GG_rows = Filter_GG_AdURL(urlTotalGG, start_, sampleRandom, urlGG_existing)
start_ += len(GG_rows)

MS_rows = Filter_MS_AdURL(urlMS, start_, sampleRandom, urlMS_existing)
start_ += len(MS_rows)

TT_rows = Filter_TT_X_AdURL(urlTT, "ttclid", start_, sampleRandom, urlTT_existing)
start_ +=  len(TT_rows)

TW_rows = Filter_TT_X_AdURL(urlTW, "twclid", start_, sampleRandom, urlTW_existing)
start_ += len(TW_rows)

YH_rows = Filter_YH_AdURL(f"adURLs/yahoo_redirects_round{str(round)}.csv", start_, sampleRandom, "adURLs/yahoo_redirects_adhoc.csv")
start_ += len(YH_rows)


write_file(MS_rows, MS_SELECTED_VISIT_ADS, ADHOC_MS_SELECTED_VISIT_ADS)
write_file(TT_rows, TT_SELECTED_VISIT_ADS, ADHOC_TT_SELECTED_VISIT_ADS)
write_file(TW_rows, TW_SELECTED_VISIT_ADS, ADHOC_TW_SELECTED_VISIT_ADS)
write_file(FB_rows, FB_SELECTED_VISIT_ADS, ADHOC_FB_SELECTED_VISIT_ADS)
write_file(YH_rows, YH_SELECTED_VISIT_ADS, ADHOC_YH_SELECTED_VISIT_ADS)
write_file(GG_rows, GG_SELECTED_VISIT_ADS, ADHOC_GG_SELECTED_VISIT_ADS)