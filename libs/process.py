from anyio import Path
from libs.helpers import is_infinite_scroll_page, scroll_infinite, slow_scroll_page
from libs.captureAds import capture_marked_elements, capture_marked_elements_lite, capture_marked_elements_nonDB
from libs.browser import init_browser, close_and_delete_profile
from libs.helpers import unzip_profile
from libs.internal import get_internal_links
import os, random
from libs.dbProcess import get_db_conn, save_network_data, insert_run, upsert_page
import time, threading
from urllib.parse import urlparse, parse_qs, unquote

def performance_log_listener(driver, events, stop_event, after_flag, poll_interval=0.25, max_events=40000):
    import json, time
    from selenium.common.exceptions import WebDriverException

    while not stop_event.is_set():
        if len(events) >= max_events:
            break

        try:
            logs = driver.get_log("performance")
        except WebDriverException:
            break
        except Exception:
            break

        for entry in logs:
            if len(events) >= max_events:
                break
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method", "").startswith("Network."):
                    msg["_after"] = after_flag["value"]
                    events.append(msg)
            except Exception:
                continue

        stop_event.wait(poll_interval)
        #time.sleep(poll_interval)





def stepsEachUrl(driver, url, outdir, timeoutLoad=20, timeoutVisit=10, max_idle=3):
    print(f"[INFO] Navigating to {url}...")
    driver.set_page_load_timeout(timeoutLoad)
    #driver.get(url)
    #safeGet(driver, url, timeoutLoad)
            
    driver.get(url)
    
    time.sleep(timeoutVisit)  # initial wait for page load


    js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
    driver.execute_script(js)

    scroll = True

    if scroll:
        if is_infinite_scroll_page(driver):
            print("[INFO] Page detected as INFINITE SCROLL.")
            scroll_infinite(driver, max_idle=max_idle) 
        else:
            print("[INFO] Page is NORMAL scroll.")
            slow_scroll_page(driver)

    #slow_scroll_page(driver, step=300, pause=1.0)
    time.sleep(10)
    csv_path = os.path.join(outdir,"metadata.csv")
    
    
    capture_marked_elements(driver, outdir=outdir, csv_path=csv_path)

def stepsEachUrl_lite(driver, url, outdir, timeoutLoad=30, timeoutVisit=10, subpage=False, screenshot=False, max_idle=3, bing_mode=False, yahoo_mode=False):
    import time
    print(f"[INFO] Navigating to {url}...")
    if subpage:
        timeoutLoad = timeoutLoad
    else:
        timeoutLoad = timeoutLoad
    driver.set_page_load_timeout(timeoutLoad)

    
    driver.get(url)
    # try:
    #     driver.get(url)
    # except:
    #     driver.execute_script("window.stop();")   # <<< Dừng load
    
    time.sleep(timeoutVisit)  # initial wait for page load

        
    js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
    driver.execute_script(js)


    scroll = True
    BingYahoo = bing_mode or yahoo_mode
    if BingYahoo:
        scroll_infinite(driver,lite_mode=True, max_idle=max_idle)

    if scroll and BingYahoo==False:
        if is_infinite_scroll_page(driver):
            print("[INFO] Page detected as INFINITE SCROLL.")
            scroll_infinite(driver,lite_mode=True, max_idle=max_idle)   # Hàm scroll dành riêng cho trang vô tận
        else:
            print("[INFO] Page is NORMAL scroll.")
            slow_scroll_page(driver,lite_mode=True)  # Hàm scroll hiện tại của bạn

    time.sleep(5)
    
    capture_marked_elements_lite(driver, outdir=outdir, screenshot=screenshot, bing_mode=bing_mode, yahoo_mode=yahoo_mode)


def stepsEachUrl_dynamicGCLID(driver, url, outdir, timeoutLoad=30, timeoutVisit=10, subpage=False, screenshot=False):
    import time
    print(f"[INFO] Navigating to {url}...")
    if subpage:
        timeoutLoad = timeoutLoad
    else:
        timeoutLoad = timeoutLoad
    driver.set_page_load_timeout(timeoutLoad)

    
    driver.get(url)
    # try:
    #     driver.get(url)
    # except:
    #     driver.execute_script("window.stop();")   # <<< Dừng load
    
    time.sleep(timeoutVisit)  # initial wait for page load

        
    js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
    driver.execute_script(js)


    scroll = True

    if scroll:
        if is_infinite_scroll_page(driver):
            print("[INFO] Page detected as INFINITE SCROLL.")
            scroll_infinite(driver,lite_mode=True)   # Hàm scroll dành riêng cho trang vô tận
        else:
            print("[INFO] Page is NORMAL scroll.")
            slow_scroll_page(driver,lite_mode=True)  # Hàm scroll hiện tại của bạn

    time.sleep(5)

    from libs.captureAds import capture_marked_elements_dynamicGCLID
    
    capture_marked_elements_dynamicGCLID(driver, outdir=outdir, screenshot=screenshot)


def stepsEachUrl_nonDB(driver, url, outdir, timeoutLoad=30, timeoutVisit=10):
    import time
    print(f"[INFO] Navigating to {url}...")
    driver.set_page_load_timeout(timeoutLoad)
    #driver.get(url)
    #safeGet(driver, url, timeoutLoad)

    events = []
    stop_event = threading.Event()

    listener = threading.Thread(target=performance_log_listener, args=(driver, events, stop_event), daemon=True)
    listener.start()

    
    try:
        driver.get(url)
        # try:
        #     driver.get(url)
        # except:
        #     driver.execute_script("window.stop();")   # <<< Dừng load
    
        time.sleep(timeoutVisit)  # initial wait for page load

        
        js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
        driver.execute_script(js)



        scroll = True

        if scroll:
            if is_infinite_scroll_page(driver):
                print("[INFO] Page detected as INFINITE SCROLL.")
                scroll_infinite(driver)   # Hàm scroll dành riêng cho trang vô tận
            else:
                print("[INFO] Page is NORMAL scroll.")
                slow_scroll_page(driver)  # Hàm scroll hiện tại của bạn

        #slow_scroll_page(driver, step=300, pause=1.0)
        time.sleep(timeoutVisit)
        csv_path = os.path.join(outdir,"metadata.csv")
    

        capture_marked_elements_nonDB(driver, outdir=outdir, csv_path=csv_path)

    finally:
        try:
            driver.execute_script("window.stop();")
        except:
            try:
                driver.execute_cdp_cmd("Page.stopLoading", {})
            except Exception as e:
                print(e)
                pass
        
        stop_event.set()
        listener.join(timeout=3)

    print(f"[INFO] Collected {len(events)} network events")


def stepsEachUrl_test(driver, id_site, url, outdir, timeoutLoad=30, timeoutVisit=10):
    import time
    print(f"[INFO] Navigating to {url}...")
    driver.set_page_load_timeout(timeoutLoad)
    #driver.get(url)
    #safeGet(driver, url, timeoutLoad)

    events = []
    stop_event = threading.Event()

    listener = threading.Thread(target=performance_log_listener, args=(driver, events, stop_event), daemon=True)
    listener.start()

    with get_db_conn() as conn:
        page_id = upsert_page(conn, id_site = id_site, page_url = url, title = driver.title)
        run_id = insert_run(conn, id_site = id_site, page_id = page_id, page_url=url)

    
    try:
        driver.get(url)
        time.sleep(timeoutVisit)  # initial wait for page load

        
        js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
        driver.execute_script(js)


        scroll = True

        if scroll:
            if is_infinite_scroll_page(driver):
                print("[INFO] Page detected as INFINITE SCROLL.")
                scroll_infinite(driver)
            else:
                print("[INFO] Page is NORMAL scroll.")
                slow_scroll_page(driver)

        #slow_scroll_page(driver, step=300, pause=1.0)
        time.sleep(timeoutVisit)
        csv_path = os.path.join(outdir,"metadata.csv")
    

        with get_db_conn() as conn:
            capture_marked_elements(driver, conn=conn, id_site=id_site, run_id=run_id, outdir=outdir, csv_path=csv_path)

    finally:
        try:
            driver.execute_script("window.stop();")
        except:
            try:
                driver.execute_cdp_cmd("Page.stopLoading", {})
            except Exception as e:
                print(e)
                pass
        
        stop_event.set()
        listener.join(timeout=3)

    print(f"[INFO] Collected {len(events)} network events")
    
    try:
        with get_db_conn() as conn:    
            save_network_data(conn, id_site, run_id, url, events)
            with conn.cursor() as cur:
                cur.execute("""UPDATE runs SET status='success', run_end_time=NOW() WHERE run_id=%s""", (run_id,))
    except Exception as e:
        with get_db_conn() as conn:
            with conn.cursor() as cur:#
                cur.execute("""
                    UPDATE runs
                    SET status='failed', notes=%s, run_end_time=NOW()
                    WHERE run_id=%s
                """, (str(e), run_id))
        raise


def create_only_driver(profile_dir, headless, extension_unpacked_folder=None, page_load_strategy="normal"):
    from pathlib import Path
    BASE_DIR = Path(__file__).parent.parent
    if extension_unpacked_folder is None:
        EXT_PATH = BASE_DIR / "extensions" / "DetectAds"
    else:
        EXT_PATH = BASE_DIR / "extensions" / extension_unpacked_folder
    EXT_PATH = str(EXT_PATH)

    driver = None
    for attemp in range(2):
        try:
            driver = init_browser(user_data_dir=profile_dir,headless=headless, extension_unpacked_folder=EXT_PATH, version_main=153, page_load_strategy=page_load_strategy)
            break
        except Exception as e:
            print(f"Error in create driver: {e} \nTry again")
            time.sleep(5)

    return driver



def get_public_ips():
    import requests
    ipv4 = requests.get("https://api.ipify.org", timeout=5).text
    #ipv6 = requests.get("https://api64.ipify.org", timeout=5).text

    return ipv4
    #return {
    #    "ipv4": ipv4,
    #    "ipv6": ipv6
    #}

def runTest_lite(driver, target_url, outdir, max_Pages, timeoutLoad, timeoutVisit, screenshot=False, max_idle=3, bing_mode=False, yahoo_mode=False):
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    outdir_target = os.path.join(outdir, site)
    os.makedirs(outdir_target, exist_ok=True)

    visited = set()
    stepsEachUrl_lite(driver, target_url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit, screenshot=screenshot, max_idle=max_idle, bing_mode=bing_mode, yahoo_mode=yahoo_mode)
        
    visited.add(driver.current_url)
    pool = get_internal_links(driver, driver.current_url)

    if not pool:
        print("No internal links found.")
        return

    print(f"Found {len(pool)} internal links.")
    random.shuffle(pool)

    for url in pool:
        if len(visited) >= max_Pages:
            break

        if url in visited:
            continue

        print(f"[MASTER] Visiting next URL: {url}")
        try:
            stepsEachUrl_lite(driver, url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit, subpage=True, screenshot=screenshot, max_idle=max_idle)
        except Exception as e:
            print(f"[WARN] Failed to process {url}: {e}")

        visited.add(url)
    print(f"Finished visiting {len(visited)} pages.")


def runGCLID(driver, target_url, outdir, timeoutMins, timeoutLoad, timeoutVisit, screenshot=False, max_idle=3, bing_mode=False, yahoo_mode=False):
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    outdir_target = os.path.join(outdir, site)
    os.makedirs(outdir_target, exist_ok=True)

    visited = set()
    start = time.time()
    stepsEachUrl_lite(driver, target_url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit, screenshot=screenshot, max_idle=max_idle, bing_mode=bing_mode, yahoo_mode=yahoo_mode)
        
    visited.add(driver.current_url)
    pool = get_internal_links(driver, driver.current_url)

    if not pool:
        print("No internal links found.")
        return

    print(f"Found {len(pool)} internal links.")
    random.shuffle(pool)

    while time.time() - start < timeoutMins*60:
        for url in pool:
            if url in visited:
                continue

            print(f"[MASTER] Visiting next URL: {url}")
            try:
                stepsEachUrl_lite(driver, url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit, subpage=True, screenshot=screenshot, max_idle=max_idle)
            except Exception as e:
                print(f"[WARN] Failed to process {url}: {e}")

            visited.add(url)
        if len(visited) >= len(pool):
            break
    print(f"Finished visiting {len(visited)} pages.")



def runTest_dynamicGCLID(driver, target_url, outdir, max_Pages, timeoutLoad, timeoutVisit, screenshot=False):
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    #https://www.googleadservices.com/pagead/aclk?sa=L&ai=C2pubeuLBaeORDLyYjeYPyuX1oAOav8fUhAHs6Ie6hROEwbWrrgEQASDo5YkTYKWAgICcAaABv8DYvCnIAQmpAnLWtklPg7M-4AIAqAMByAMKqgTLAk_QR8ItX2s1AjUhp2Ww8YLzTwXD01B3QxOuhBjK5asTFYwMrx66KLbMjAdTYRONtcDQVAebzp2YoCASCPaLafEOdqwMLkFzTlStqP7fp7NUBIk4_1Rl2irwGSLvUXPkeCZTNZCG37PBS_Iq-d8W4Fz3Xb4lYeWyV-8o0ChZIh_LNTQQaBvqyO8rDJqfEJKHPuNAnRo4SlQOOhotZ1tSyI-1OHjOk9pnR9BEuJc8HQ_l1mgwMOwfkURENJp-mvPX4Nw6ddAoFVE19jJcZYMFWReG8FWwIBVfcAf4AGlidH1mPP_yAOuVZcOIooz4k5A-0O7KOsoOIp3y6LkgYWvmDwqhtfsOG47Sr91HUu3IlH0fzu8jl7qyJig8-2P_p-IIhNHy1wzGuSHDOBnYe9ijlvdCVC1xl7BWfKvPbwJP-gb1rDH0GZMylIz19q_ABNqc3O-EBeAEAYgFmpG3sU6gBi6AB7_4qJwEqAenzLECqAfi2LECqAemvhuoB8zOsQKoB_PRG6gHltgbqAeqm7ECqAeOzhuoB5PYG6gH8OAbqAfulrECqAf-nrECqAevvrECqAfVyRuoB9m2sQKoB5oGqAf_nrECqAffn7ECqAf4wrECqAf7wrEC2AcA0ggyCIDhgBAQARidATIIqoKAgICAgAg6DoDAA4CAhICAlK7gA6gHSL39wTpY0Z2CkKu3kwOxCYOID_ePtbkggAoDmAsByAsBgAwBogwDkAEBqg0CQVXIDQHiDRMIvM2CkKu3kwMVPEzDBh3Kch006g0TCLSMhZCrt5MDFTxMwwYdynIdNPANAogO____________AbAOxsv7rRjYEwvQFQGYFgHKFgIKAPgWAYAXAbIXDhgBKgoxOTk4ODE0MDU2uhcCOAGqGBcJAAAAANCBA0ESCjE5OTg4MTQwNTYYAbIYCRIChVQYLiIBANAYAegYAcIZAggB&ae=1&gclid=EAIaIQobChMI47aUkKu3kwMVPEzDBh3Kch00EAEYASAAEgKbrPD_BwE&num=1&cid=CAQSbwAFq6B9mOa5V3A5idiZtJjAK8q3t9vqdI8pl6krecFPZaDvChZtOMNrho_1QSF7OuAV7w_TZcGqN0dhtp6E68XLiNWGK15LCtP4HunfB5vQVOL0IKc2beJwmF6V98iHtLYizoqyLdnoLx8YqHBhdhgB&sig=AOD64_1h4BxkZlgsxAahKr3wjfCAE97MTw&client=ca-pub-2615941022292182&rf=4&nb=9&adurl=https://makesyoufluent.com/es/%3Fcmpid%3D64f9b76b96406f000150b821%26sub1%3D3_MYF_All_pMax_LS%26sub2%3D%26sub3%3D%26sub4%3D%26sub5%3D%26sub6%3D21041627514%26sub7%3Dc%26sub8%3D%26sub9%3Dx%26sub10%3D%26ref_id%3DEAIaIQobChMI47aUkKu3kwMVPEzDBh3Kch00EAEYASAAEgKbrPD_BwE%26gad_source%3D5%26gad_campaignid%3D21041629338%26gclid%3DEAIaIQobChMI47aUkKu3kwMVPEzDBh3Kch00EAEYASAAEgKbrPD_BwE
    outdir_target = os.path.join(outdir, site)
    os.makedirs(outdir_target, exist_ok=True)

    try:
        stepsEachUrl_dynamicGCLID(driver, target_url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit, screenshot=screenshot)
    
    except Exception as e:
        print("Error: ",e)



def runTest_nonDB(driver, target_url, outdir, max_Pages, timeoutLoad, timeoutVisit):
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    outdir_target = os.path.join(outdir, site)
    os.makedirs(outdir_target, exist_ok=True)

    visited = set()
    try:
        stepsEachUrl_nonDB(driver, target_url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit)
        visited.add(driver.current_url)
        pool = get_internal_links(driver, driver.current_url)

        if not pool:
            print("No internal links found.")
            return

        print(f"Found {len(pool)} internal links.")
        random.shuffle(pool)

        for url in pool:
            if len(visited) >= max_Pages:
                break

            if url in visited:
                continue

            print(f"[MASTER] Visiting next URL: {url}")
            try:
                stepsEachUrl_nonDB(driver, url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit)
            except Exception as e:
                print(f"[WARN] Failed to process {url}: {e}")

            visited.add(url)
        print(f"✅ Finished visiting {len(visited)} pages.")
    
    except Exception as e:
        print("Error: ",e)


def runTest(driver, id_site, target_url, outdir, max_Pages, ip, timeoutLoad, timeoutVisit):
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    outdir_target = os.path.join(outdir, site)
    os.makedirs(outdir_target, exist_ok=True)

    visited = set()
    try:
        stepsEachUrl_test(driver, id_site, target_url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit)
        visited.add(driver.current_url)
        pool = get_internal_links(driver, driver.current_url)

        if not pool:
            print("No internal links found.")
            return

        print(f"Found {len(pool)} internal links.")
        random.shuffle(pool)

        for url in pool:
            if len(visited) >= max_Pages:
                break

            if url in visited:
                continue

            print(f"[MASTER] Visiting next URL: {url}")
            try:
                stepsEachUrl_test(driver, id_site, url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit)
            except Exception as e:
                print(f"[WARN] Failed to process {url}: {e}")

            visited.add(url)
        print(f"Finished visiting {len(visited)} pages.")
    
    except Exception as e:
        print("Error: ",e)


def runDetectAds(driver, target_url, outdir, timeoutLoad, timeoutVisit):
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    outdir_target = os.path.join(outdir, site)
    os.makedirs(outdir_target, exist_ok=True)


    try:
        stepsEachUrl_test(driver, target_url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit)
    except Exception as e:
        print("Error: ",e)
    #finally:
    #    input("Please enter to quit!")




def run(config, target_url):
    names = config["names"]
    numOfDrivers = len(config["profiles_zip"])
    
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    outdir_target = os.path.join(config["outdir"], site)
    os.makedirs(outdir_target, exist_ok=True)

    profiles_dirs = []
    for profile_zip in config["profiles_zip"]:
        dir = unzip_profile(profile_zip)
        profiles_dirs.append(dir)

    drivers = []
    for i in range(numOfDrivers):
        driver = init_browser(user_data_dir=profiles_dirs[i],headless=config["headless"])
        drivers.append(driver)

        #har_collectors.append(HarCollector(driver,har_name=f"browser_{i}"))
    
    visited = set()

    try:
        for i in range(numOfDrivers):
            mode = names[i]
            driver = drivers[i]
            outdir_driver = os.path.join(outdir_target, names[i])
            stepsEachUrl(driver, target_url, outdir_driver, mode=mode, timeoutLoad=config["timeoutLoad"], timeoutVisit=config["timeoutVisit"])

        
        visited.add(drivers[0].current_url)
        
        pool = get_internal_links(drivers[0], drivers[0].current_url)

        if not pool:
            print("No internal links found.")
            return
        
        print(f"Found {len(pool)} internal links.")
        random.shuffle(pool)

        for url in pool:
            if len(visited) >= config["max_Pages"]:
                break

            if url in visited:
                continue

            print(f"[MASTER] Visiting next URL: {url}")
            for i in range(numOfDrivers):
                driver = drivers[i]
                outdir_driver = os.path.join(outdir_target, names[i])
                try:
                    stepsEachUrl(driver, url, outdir_driver, config["timeoutLoad"], config["timeoutVisit"])
                except Exception as e:
                    print(f"[WARN] Failed to process {url} on driver: {e}")

            visited.add(url)
        print(f"✅ Finished visiting {len(visited)} pages.")


    finally:
        for i in range(numOfDrivers):
            driver = drivers[i]
            dir = profiles_dirs[i]
            close_and_delete_profile(driver, dir)





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

    return result

def has_msclkid(url):
    try:
        # tracking URL
        q1 = parse_qs(urlparse(url).query)

        if q1.get("rtype", [""])[0] != "targetURL":
            return False

        # rlink
        rlink = unquote(q1["rlink"][0])

        # aclick
        q2 = parse_qs(urlparse(rlink).query)

        target = unquote(q2.get("u", [""])[0])

        return "msclkid=" in target.lower()

    except Exception:
        return False

def filter_yahoo_urls(urls):
    result = set()
    for url in urls:
        if url.startswith("https://apm.yahoo.co.jp/rd?"):
            result.add(url)

    return result

