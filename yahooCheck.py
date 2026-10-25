import asyncio
from pathlib import Path
import aiohttp
import csv
from urllib.parse import urlparse, parse_qs
import tldextract

folder_path = Path("adURLs")

async def fetch_final_url(session, url, semaphore):
    async with semaphore:
        try:
            async with session.get(url,allow_redirects=True,timeout=aiohttp.ClientTimeout(total=20)) as response:
                dest_url = str(response.url)
                ext = tldextract.extract(dest_url)
                if ext.domain and ext.suffix:
                    domain = f"{ext.domain}.{ext.suffix}"
                else:
                    domain = ""
                
                yclid = ""
                try:
                    query_params = parse_qs(urlparse(dest_url).query)
                    if "yclid" in query_params:
                        yclid = query_params["yclid"][0]

                except Exception:
                    pass
                return {
                    "source_url": url,
                    "dest_url": str(response.url),
                    "domain": domain,
                    "yclid": yclid
                }

        except Exception as e:
            return {
                "source_url": url,
                "dest_url": "",
                "domain": "",
                "yclid": ""
            }


async def resolve_urls(url_list, output_file="yahoo_redirects.csv",concurrency=50):

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    }

    semaphore = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency,ssl=False)

    async with aiohttp.ClientSession(headers=headers,connector=connector) as session:

        tasks = [
            fetch_final_url(session,url,semaphore)
            for url in url_list
        ]
        results = await asyncio.gather(*tasks)

    with open(output_file,"w",newline="",encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f,fieldnames=["source_url","dest_url","domain","yclid"])

        writer.writeheader()
        writer.writerows(results)

    print(f"Saved {len(results)} URLs -> {output_file}")

def collect_ads_by_folder(folder_path, round):
    urlYH = set()
    for file in folder_path.iterdir():
        if file.is_file():
            fname = str(file.name)
            if fname.startswith("YH") and fname.endswith(f"_round{str(round)}.csv"):
                with open(file,"r", encoding="utf-8") as f:
                    for line in f:
                        urlYH.add(line.strip())
            else:
                continue
    return urlYH

round = input("Enter num of round: ")
urls = collect_ads_by_folder(folder_path=folder_path, round=round)
output_file = f"adURLs/yahoo_redirects_round{str(round)}.csv"

asyncio.run(resolve_urls(urls,output_file,concurrency=50))