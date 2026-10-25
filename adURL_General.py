import time
from libs.process import create_only_driver
from libs.helpers import unzip_profile
from urllib.parse import urlparse, parse_qs, parse_qsl, unquote
import argparse, random
from pathlib import Path
from libs.cleanup import cleanup_driver
from libs.internal import get_internal_links
from libs.captureAds import BingYahoo_capture_marked_elements, GoogleAds_capture_marked_elements
from selenium.common.exceptions import StaleElementReferenceException

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import shutil

def multi_decode(url, max_rounds=5):
    previous = url
    for _ in range(max_rounds):
        decoded = unquote(previous)
        if decoded == previous:
            break
        previous = decoded
    return previous


def extract_params_from_url(url):
    all_params = []
    decoded_url = multi_decode(url)

    parsed = urlparse(decoded_url)
    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    for k, v in query_params:
        all_params.append({"name": k, "value": v})
    if ";" in parsed.path:
        parts = parsed.path.split(";")[1:]
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                all_params.append({"name": k, "value": v})

    return all_params


checkCCBaner = [
    {"site":"https://nytimes.com", "country":["AU", "BR", "DE"]},
    {"site":"https://cnn.com", "country":["US", "BR", "DE"]},
    {"site":"https://theguardian.com", "country":["AU", "US", "BR", "DE", "JP", "ZA"]},
    {"site":"https://weather.com", "country":["DE","BR"]},
    {"site":"https://bbc.com", "country":["AU", "BR", "DE"]}
]


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl AdURLs from Google, Yahoo, Microsoft")
    parser.add_argument("--profile-zip", help="Name of the Chrome profile ZIP file to use. The file must exist inside the default 'profiles/' directory. ")
    parser.add_argument("--timeoutMins", type=int, default=5, help="Page visit (mins). Default: 5 mins")
    parser.add_argument("--timeout", type=int, default=30, help="TimeoutToGetElement")
    parser.add_argument("--round", type=int, default=1, help="Num of round")
    parser.add_argument("--pause", type=int, default=30, help="Pause time. Default 30s")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--country", required=True, help="Country code")
    parser.add_argument("--autoRun", type=int, default=1, help="Run auto (default: 1)")
    parser.add_argument("--yahoo", action="store_true")
    parser.add_argument("--microsoft", action="store_true")
    parser.add_argument("--site", help="Adress URL")
    
    return parser.parse_args()

def push_priority_urls(urls):
    exclude_nytimes = ["?page=", "/section", "/spotlight", "/topic", "/newsletters", "/column", "/video", "/news-event", "/subscription", "/games", "/sitemap", "/by", "/subscription", "/es"]
    exclude_theguardian = ["/email-newsletters"]
    exclude_weather = ["/data-rights","/accessibility-statement","/failover","/sitemap","/data-vendors","/ad-choices","/storm-radar"]
    priority_urls = []
    other_urls = []
    for url in urls:
        if "bbc.com" in url:
            if "/reel/video/" in url or "/videos/" in url:
                continue
            elif "/article/" in url or "/articles/" in url:
                priority_urls.append(url)
            else:
                other_urls.append(url)
        elif "cnn.com" in url:
            if "/audio/podcasts" in url or "/video" in url or "/videos" in url or "/accessibility" in url or "transcripts." in url:
                continue
            else:
                other_urls.append(url)
        elif "nytimes.com" in url:
            if any(x in url for x in exclude_nytimes):
                continue
            else:
                other_urls.append(url)

        elif "theguardian.com" in url:
            if any(x in url for x in exclude_theguardian):
                continue
            else:
                other_urls.append(url)

        elif "weather.com" in url:
            if any(x in url for x in exclude_weather):
                continue
            else:
                other_urls.append(url)

        else:
            other_urls.append(url)

    return priority_urls + other_urls

def main():
    google = False
    args = parse_args()
    profile_name = args.profile_zip
    timeoutMins = args.timeoutMins
    round = args.round
    pause = args.pause
    headless = args.headless
    country = args.country
    autoRun = args.autoRun
    yahoo = args.yahoo
    microsoft = args.microsoft
    timeout = args.timeout

    if microsoft and yahoo:
        print("Error!")
        return
    elif microsoft or yahoo:
        if microsoft:
            platform = "MS"
        else:
            platform = "YH"
    else:
        google = True
        platform = "GG"


    OUTPUT_CSV = f"adURLs/{platform}_AdUrl_{country}_round{round}.csv"
    OUTPUT_TOTAL_CSV = f"adURLs/TOTAL_{platform}_AdUrl_{country}_round{round}.csv"

    # strRound = str(round)
    # base_dir = f"captures_round_YH_{strRound}"

    BASE_DIR = Path(__file__).resolve().parent
    PROFILES_DIR = BASE_DIR / "profiles"
    if not PROFILES_DIR.is_dir():
        raise RuntimeError(f"'profiles/' directory does not exist: {PROFILES_DIR}")

    if not profile_name.endswith(".zip"):
        profile_name += ".zip"

    profiles_zip = PROFILES_DIR / profile_name

    # ZIP must exist
    if not profiles_zip.is_file():
        raise RuntimeError(f"Profile ZIP not found: {profiles_zip}")

    profiles_zip = str(profiles_zip)

    print(f"[INFO] Using profile ZIP: {profiles_zip}")
    profile_dir = unzip_profile(profiles_zip)
        


    if yahoo:
        site = "https://www.yahoo.co.jp"
    if microsoft:
        site = "https://www.msn.com"
    if google:
        site = args.site
        if site is None:
            print("Error!!")
            return
    # max_Pages = 1
    
    if yahoo or microsoft:
        extension_name = "DetectAds_Upgrade"
        page_load_strategy = "normal"
    else:
        extension_name = "DetectAds"
        page_load_strategy="normal"

    visited_total = []

    for i in range(autoRun):
        #print(f"[INFO] Creating browser driver {i}...")
        driver = None
        print(f"Run no {i}")
        driver = create_only_driver(profile_dir, headless, extension_unpacked_folder=extension_name, page_load_strategy=page_load_strategy)
        if driver is None:
            print("CAN NOT CREATE DRIVER! QUIT PROCESS!")
            exit()
            

        print(f"[INFO] Browser driver created.")
        try:
            #----- cookie banner
            driver.get(site)
            if yahoo or microsoft:
                time.sleep(3)
            else:
                time.sleep(10)

            if microsoft and country in ["DE", "BR", "ZA"]:
                click_accept_button(driver)
                time.sleep(8)
                driver.refresh()
                time.sleep(3)
        
            if google:
                check = False
                for c in checkCCBaner:
                    if c["site"] == site and country in c["country"]:
                        check = True
                        break

                if check:
                    print("[COOKIE BANNER] Check Cookie Banner...")
                    status = click_accept_buttonGG(driver, timeout=timeout)
                    time.sleep(8)

                    driver.refresh()
                    if "theguardian" in driver.current_url:
                        time.sleep(2)
                        try:
                            button = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(),'Collapse banner')]]")))
                            try:
                                button.click()
                            except:
                                driver.execute_script("arguments[0].click();", button)
                            print("Collapse banner clicked")
                        except TimeoutException:
                            pass
                    time.sleep(10)

            #----- main


            start = time.time()

            js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
            driver.execute_script(js)

            subpages = False
            visited = set()
            while (time.time() - start) < (timeoutMins*60):
                old_y = driver.execute_script("return window.pageYOffset")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                   
                remaining = timeoutMins * 60 - (time.time() - start)
                if remaining <= 0:
                    break
                time.sleep(min(pause, remaining))

                if yahoo or microsoft:
                    hrefs = BingYahoo_capture_marked_elements(driver, screenshot=False)
                    driver.execute_script(f"window.scrollTo(0, {old_y});")
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                if google:
                    hrefs = GoogleAds_capture_marked_elements(driver, screenshot=False)

                if hrefs:
                    save_to_csv(hrefs, OUTPUT_TOTAL_CSV)
                    if yahoo:
                        yahoo_urls = filter_yahoo_urls(hrefs)
                        save_to_csv(yahoo_urls, OUTPUT_CSV)
                    if microsoft:
                        bing_urls = filter_bing_urls(hrefs)
                        save_to_csv(bing_urls, OUTPUT_CSV)
                    if google:
                        google_urls = filter_google_urls(hrefs)
                        save_to_csv(google_urls, OUTPUT_CSV)
            
                new_y = driver.execute_script("return window.pageYOffset")
                print(f"old: {old_y} - new: {new_y}")
                if old_y == new_y:
                    subpages = True
                    visited.add(driver.current_url)
                    stop = time.time()
                    break

                time.sleep(1)

            if subpages:
                pool = get_internal_links(driver, driver.current_url)
                if not pool:
                    print("No internal links found.")
                    # == Quit browser
                    time.sleep(2)
                    try:
                        driver.quit()
                    except:
                        pass

                    time.sleep(10)
                    continue

                remainTime = timeoutMins*60 - (stop-start)
                shuffled_pool = random.sample(pool, k=len(pool))
                pool_high_priority = push_priority_urls(shuffled_pool)
                for u in pool_high_priority:
                    print(remainTime)
                    if u in visited or (u in visited_total and google):
                        continue

                    if remainTime <= pause:
                        break

                    start_ = time.time()
                    driver.get(u)
                    
                    if "theguardian" in driver.current_url:
                        time.sleep(2)
                        try:
                            button = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(),'Collapse banner')]]")))
                            try:
                                button.click()
                            except:
                                driver.execute_script("arguments[0].click();", button)
                            print("Collapse banner clicked")
                        except TimeoutException:
                            pass
                    time.sleep(2)

                    js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
                    driver.execute_script(js)

                    while(time.time() - start_) < remainTime:
                        old_y = driver.execute_script("return window.pageYOffset")
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                            
                        remaining = remainTime - (time.time() - start_)
                        if remaining <=0:
                            break
                        time.sleep(min(pause, remaining))

                        if yahoo or microsoft:
                            hrefs = BingYahoo_capture_marked_elements(driver, screenshot=False)

                        if google:
                            hrefs = GoogleAds_capture_marked_elements(driver, screenshot=False)

                        if hrefs:
                            save_to_csv(hrefs, OUTPUT_TOTAL_CSV)
                            if yahoo:
                                yahoo_urls = filter_yahoo_urls(hrefs)
                                save_to_csv(yahoo_urls, OUTPUT_CSV)
                            if microsoft:
                                bing_urls = filter_bing_urls(hrefs)
                                save_to_csv(bing_urls, OUTPUT_CSV)
                            if google:
                                google_urls = filter_google_urls(hrefs)
                                save_to_csv(google_urls, OUTPUT_CSV)
                                        
                        new_y = driver.execute_script("return window.pageYOffset")
                        if old_y == new_y:
                            remainTime = remainTime - (time.time()-start_)
                            break
                    else:
                        remainTime = remainTime - (time.time()-start_)

                    visited.add(u)
                    if google:
                        visited_total.append(u)
            time.sleep(2)
        except Exception as e:
            pass

        # == Quit browser

        cleanup_driver(driver=driver, driver_path = None)
        time.sleep(10)

    cleanup_driver(driver=None, driver_path=None)
    for _ in range(5):
        try:
            shutil.rmtree(profile_dir)
            print("Deleted:", profile_dir)
            break
        except Exception as e:
            print("Retry delete:", e)
            time.sleep(0.5)
    print(f"[INFO] All {autoRun} runs processed.")

def save_to_csv(urls, filename):
    existing_items0 = set()
    with open(filename, 'a+', encoding='utf-8') as file:
        file.seek(0)  # Move the cursor to the beginning of the file
        for line in file:
            line = line.strip()
            if line:
                existing_items0.add(line)
    
        for item in urls:
            if item not in existing_items0:
                file.write(f"{item}\n") # Use an f-string to append a newline


def filter_yahoo_urls(urls):
    result = set()
    for url in urls:
        if url.startswith("https://apm.yahoo.co.jp/rd?"):
            result.add(url)

    return result

def filter_bing_urls(urls):
    result = []
    for url in urls:
        try:
            p = urlparse(url)

            if not (p.hostname or "").endswith("bing.com"):
                continue
            if parse_qs(p.query).get("rtype", [""])[0] == "targetURL":
                result.append(url)

        except Exception as e:
            print(f"[ERR] filter_bing_urls(): {e} - {url}")

    result_set = set(result)

    return result_set


def clickButton(driver, btn):
    try:
        btn.click()
    except Exception as e:
        #print(e)
        try:
            driver.execute_script("arguments[0].click();", btn)
            #print("Click accept button (JS)")
        except Exception as e:
            print(e)
        

        
def click_accept_buttonGG(driver, timeout=10):
    id_nytimes = "fides-accept-all-button"
    id_cnn = "onetrust-accept-btn-handler"

    id = False

    url = driver.current_url
    if "nytimes" in url:
        button_id = id_nytimes
        id = True
    elif "cnn" in url:
        button_id = id_cnn
        id = True
    else:
        id = False

    try:
        if id:
            try:
                buttons = WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.ID, button_id)))
            except TimeoutException:
                if "cnn" in url:
                    try:
                        btn = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, "//a[@role='button' and normalize-space()='Agree']")))
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click();", btn)
                            print("Click processed")
                            return True
                        else:
                            return False
                    except TimeoutException:
                        buttons = []
                        return False
                else:
                    buttons = []
                    return False
            for btn in buttons:
                if btn.is_displayed():
                    clickButton(driver, btn)
                    break

        else:
            if "theguardian" in url or "weather" in url:
                try:
                    iframes = WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.TAG_NAME, "iframe")))
                    for frame in iframes:
                        try:
                            driver.switch_to.frame(frame)
                            buttons = driver.find_elements(By.CSS_SELECTOR, 'button[title="Accept all"]')
                            buttons.extend(driver.find_elements(By.CSS_SELECTOR, 'button[title="Yes, I accept"]'))
                            buttons.extend(driver.find_elements(By.CSS_SELECTOR, 'button[title="Continue"]'))
                            for btn in buttons:
                                if btn.is_displayed():
                                    clickButton(driver, btn)
                                    raise StopIteration
                        except TimeoutException:
                            pass
                        except StaleElementReferenceException:
                            pass
                        finally:
                            driver.switch_to.default_content()
                except StaleElementReferenceException:
                    pass
                except StopIteration:
                    pass
                except TimeoutException:
                    pass


            elif "bbc" in url:
                try:
                    buttons = WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "button[data-testid='accept-button']")))
                except TimeoutException:
                    buttons = []
                    return False
                #buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-testid='accept-button']")
                for btn in buttons:
                    if btn.is_displayed():
                        clickButton(driver, btn)
                        break
            elif "forbes" in url:
                try:
                    btn = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.ID, "ketch-banner-button-primary")))
                    #buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-testid='onetrust-accept-btn-handler']")
                    if btn.is_displayed():
                        clickButton(driver, btn)
                except TimeoutException:
                    return False
                    pass
            else:
                return False
                   
        print("Click processed")
        return True
    except Exception as e:
        print("Error finding accept button:", e)
        return False
    
    time.sleep(2)

def click_accept_button(driver, timeout=30):
    """
    Find Accept Cookie Banner
    <button id="cmp-accept-btn-handler">Aceito</button>
    """
    try:
        #buttons = driver.find_elements(By.ID, "cmp-accept-btn-handler")
        #print(len(buttons))
        button = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.ID, "cmp-accept-btn-handler")))
        if button:
            #print(button)
            try:
                button.click()
            except Exception as e:
                #print(e)
                driver.execute_script("arguments[0].click();", button)
                
            print("Click processed")
            return True
        else:
            print("Not found!")
            return False
    except Exception as e:
        return False
    
    time.sleep(2)



def is_google_ads_domain(url: str) -> bool:
    GOOGLE_AD_DOMAINS = [
        "googleadservices.com",
        "doubleclick.net",
        "googlesyndication.com",
    ]

    try:
        hostname = urlparse(url).hostname or ""
        return any(
            hostname == d or hostname.endswith("." + d)
            for d in GOOGLE_AD_DOMAINS
        )
    except Exception:
        return False

def filter_google_urls(urls):
    hrefs = set()
    for u in urls:
        if is_google_ads_domain(u):
            has_gclid = False
            has_adurl = False

            params = extract_params_from_url(u)
            for p in params:
                if p["name"].lower() == "gclid":
                    has_gclid = True
                    break

            for p in params:
                if p["name"].lower() == "adurl":
                    has_adurl = True
                    break

            if has_gclid and has_adurl:
                hrefs.add(u)

    return hrefs

if __name__ == "__main__":
    main()