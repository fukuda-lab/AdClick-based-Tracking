
URL = "https://adssettings.google.com/whythisad?source=display&reasons=AUJjZ_77Yd_nvCvDUQYEFe727JfDVuKkAX9i-khjeEX0a8ue_XWnuCtGTXPLwuhePRmcnfWb7t4ad3YkKZOC1YgHN6mE3GF9PHGG_e3nOoapphC5ZGLvU14Y3Ry2ZHS8A-fD43EtcMdPjfld9c8dPrVERnPboLPtzPdWCZh19oUH1nnWTZKBNC4q3OdT2svTRizTjEZ4_tPbrBdk4VKfVnOSjNIuhPn669U5D0fHIAj1PUPirtp_pozANYZCrBpgfe2a8ozWwDjkdeOgj0cNfU0pAgp5Lf1NBbZ6_4UkmWCNk7rUrOFlQ1_hORQpf31L_HxRkW3tbmscDETiHjP8_wB96966NGiw178PXkCA_gQZOpK6sHRcTgygyE6-mVF-deeGLbVdhebfD_qB_DFLORWqCHVlKpgIuf60ZW5wv4oyhn9H1FVCKiEHjEgH5YtdvziOTplNmkvEykzFaf9dgQD_1aoGIzu5ljuf5ZYzHPgqj1b40iluvxtpgSEiDJELtA8QnhI_L5jZakGyfLGmli0PtD2QpjBNAtc4SWLiW1TuzO7ivin8V3auNKGkjnSATxTNljOf29g0OWJq6PkBbspEWgFgOG8woLohL5vUWYbbvGV4pUpnc5RpqVqroQdbp8qzalmLGNtaigvVg8A666iHDfHMk_bYdokNE5PqLTvjBY905AkGZzOaSpwkh7-aD3V6Pr42EU_s1jQR8fBojiUbh4LMQn_PIbRPqJIXQd-cdjpb7uaiYreCQNEVNwywzVVB-vhJBnKY8NiGeMFLgtIJ4-KjGcD_X2KM9lywuJaJhnFFK7Ogfvf3jnxO--ZrnU0aroqBxmFnyF4dBVFZZZcn8D_c1d1oyOcXWNZUAMvvJ5dDiHYlTm6TpZ7wyLvZ_ODx71jZvUYEcgg4UP7AY5JIQmtAYvho9AaMYL2MGtYoxM_MnayCr3bMCtj5ihYxiXm-DUqj9gEGJY8faRci0SHO8fxbj8e5gKOFaQZ-yipLv6BmW52QJ60OJdaxgmg3znlHBuM3rUo8X2usww07_jtP6HvLNHiDkTNMNUN103wkH_6nXEOUM1HaAVBDiIe3ruucqfU4umSuS1yCoCD1zGY5X7LaEj4xFGC6DwV0E98nUA0puDmXvXECGJK5puma1z_TUZU39t1RkRfvnI-RqNhKZuA6dWMIPkMI5iVg9I2LfGL9nL20H5ildI6mbeSJM0QC5WlcT2csHP8SQXrMclSspHTOrbIVgAx9Z0laUFOiTJlD8cRjm7ckW2GLkaS-ZaZ7H62rC-q9LhhKbqdi2QGWyTLVcEuy10ck1ZQ5TsABF4dQvN-_dq4T-z00EidOAU64KM9fhAqTyuUdZ205NUQq9PQDUMZZ3_EtGqtCBQtn1jdBV_9p-uQSHw4dGHhXBLyp3xiJGabjEfgHqhg05Xoa-syEeyh7IAKLyQiOLeE89wUL5KqxTtQrpV8Fq3CfJTDZmlrL6cnvylcuxOensI81ZTPNmhSw9p5ppPqBMLTPhvIz6C-Cv4tt-iaKH_HGtoMYc9uy8ad0Ewe3GDuPXG1gnaF7giQ__rI-5cMUiCuhNz1hWHuMcSwM83_-0VE_IMTJnq3N0pKwYyD8leYZWLHJjXZMsVJ8XlXKYtUjKghhPoTw3GX1O73-7ZjrhIGAJw6IryUk-iIXdM_csSzJXAhRU0sq134FOP14-Yh6R6Lx_LnxV-YKZZPPnPUVEwlcVuO90MC7GreSg5kY_aHoyDNDqs2V1l-kTB7CaDNvR7E9nLjzaJhR75EQEQa8vFlUykmkTxfY9GMtIrxG7RweG4bo-kna9_lJALpdgoyRIoCda8E6EtkfUHFKdL56EyOJ6MElE7UCLUFDgxNryZgeCZsUrn1k3XcvVI9e6z57ComAnhlDzoYDqO5NLInwMzaWX-GIhOz1l_HDxzMb_TfSsoG0PVLTv0udKglqXtC79Hrpod0MakYJYi382PPTMuPbAto2n7bTvldXM1r0DwW_PCcmXH_JWsS06XBI0JACkfFoxmo9F7706tP15pdC3uiG8TMijYaQ9_Cdi89dRI_92H7m-QFDscH8HdDvMK_urSPZNk_E05ms9z2A7JA2HkBwMfPtJYgHMS7uNOK4GYza2MwCN128PGOuZ1Xu7ILVmwK3zazJgI99xXD_batrqibzyHzR2QV-qO-3OXF2qWEhF3hvhox3sEh6oNm7&opi=122715837"

import requests, re
from bs4 import BeautifulSoup

def get_html_soup(url: str, timeout: int = 10) -> BeautifulSoup:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()  # ném exception nếu HTTP != 200

    return BeautifulSoup(resp.text, "html.parser")

def extract_by_label(soup, label_text):
    label_text = label_text.lower()

    for div in soup.find_all("div"):
        text = div.get_text(strip=True).lower()

        if text == label_text:
            parent = div.parent
            if not parent:
                continue

            # value thường nằm trong div kế tiếp
            siblings = parent.find_all("div", recursive=False)
            for sib in siblings:
                if sib is not div:
                    return sib.get_text(strip=True)

    return None

def extract_why_this_ad(html):
    soup = BeautifulSoup(html, "html.parser")

    reasons = []

    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True).lower() == "why this ad?":
            ul = h2.find_next("ul")
            if not ul:
                return []

            for li in ul.find_all("li"):
                reasons.append(li.get_text(strip=True))
            break

    return reasons


def extract_advertiser_location(html):
    soup = BeautifulSoup(html, "html.parser")

    advertiser_raw = extract_by_label(soup, "advertiser")
    location = extract_by_label(soup, "location")

    advertiser = None
    if advertiser_raw:
        advertiser = re.sub(r"paid for by", "", advertiser_raw, flags=re.I).strip()

    return {
        "advertiser": advertiser,
        "location": location
    }



def extract_see_more_ads(html):
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        if "see more ads" in a.get_text(strip=True).lower():
            return a["href"]

    return None



def extract_google_why_this_ad(html):
    soup = BeautifulSoup(html, "html.parser")

    advertiser_raw = extract_by_label(soup, "advertiser")
    location = extract_by_label(soup, "location")

    advertiser = None
    if advertiser_raw:
        advertiser = advertiser_raw.replace("Paid for by", "").strip()

    reasons = extract_why_this_ad(html)
    see_more = extract_see_more_ads(html)

    return {
        "advertiser": advertiser,
        "location": location,
        "why_this_ad": reasons,
        "see_more_ads_url": see_more
    }


soup = get_html_soup(URL)

# Lấy toàn bộ HTML
html = soup.prettify()
#print(html)


with open("output.txt", "w", encoding="utf-8") as f:
    f.write(html)

res = extract_google_why_this_ad(html)
print(res)