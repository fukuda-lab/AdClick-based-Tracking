import threading
import os, time
from libs.browser import init_browser
from libs.getStorage import clear_all_storage
from bannerclick import bannerdetectionMOD as bc
import argparse, random
from datetime import datetime
from pathlib import Path
from selenium.common.exceptions import WebDriverException
import csv
from libs.dbProcess import get_db_conn, insert_site_GeneralAds
from libs.backupSession import importDataVisit
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import json
from libs.cleanup import cleanup_driver


strategies = ["none", "eager", "normal"]
COUNTRIES = ["US","DE","JP","AU","BR","ZA"]
PLATFORMS = ["FB","GG","MS","TT","TW","YH"]
CHOICES = [0,2,1]

DATA_CONSISTENCY = []

def getidDir(base_dir, country, date_str):
    while True:
        idDir = random.randint(10000, 99999)
        exists = any(
            Path(f"{base_dir}/{country}_{platform}_{date_str}_visitedURL_{idDir}").is_dir()
            for platform in PLATFORMS
        )

        if not exists:
            return idDir

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



def click_TW_accept_button(driver, timeout=10):
    try:
        buttons = WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.XPATH, '//button[.//div[normalize-space()="Accept all cookies"]]')))
    except TimeoutException:
        buttons = []
        return False
    
    for btn in buttons:
        if btn.is_displayed():
            clickButton(driver, btn)
            break
    
    time.sleep(2)

def click_TT_accept_button(driver, timeout=10):
    def find_button(d):
        try:
            host = d.find_element(By.CSS_SELECTOR,"tiktok-cookie-banner")

            shadow = host.shadow_root

            for button in shadow.find_elements(By.CSS_SELECTOR,"button"):
                if button.text.strip() == "Allow all":
                    return button
        except Exception:
            return False
        return False

    try:
        button = WebDriverWait(driver, timeout).until(find_button)
    except TimeoutException:
        button = None
        return False

    if button and button.is_displayed():
        clickButton(driver, button)
    time.sleep(2)



def click_FB_accept_button(driver, timeout=10):
    try:
        buttons = WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.XPATH, '//div[@role="button" and @aria-label="Allow all cookies"]')))
    except TimeoutException:
        buttons = []
        return False

    for btn in buttons:
        if btn.is_displayed():
            clickButton(driver, btn)
            break
    
    time.sleep(2)

def loadSitesFromCSV(csv_path):
    sites = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sites.append({
                "id_site": int(row["id_site"]),
                "url": row["ads_url"]
            })
    return sites

def getOutDir(platform):
    outdir = f"{base_dir}/{country}_{platform}_{date_str}_visitedURL_{idDir}"
    os.makedirs(outdir, exist_ok=False)

    print(f"[INFO] Output directory: {outdir}")
    return outdir

def watchdog(driver_ref, id_site):
    """ Kills the driver if it takes too long on a domain. """
    start_time = time.time()
    WATCHDOG_TIMEOUT = 60 * 20  # 20 minutes
    while time.time() - start_time < WATCHDOG_TIMEOUT:
        time.sleep(1)  # Check every second
        if driver_ref["done"]:  # If main thread finished, exit watchdog
            return

    # If execution time exceeds timeout, kill driver and restart
    print(f"{id_site} is stuck! Forcing driver restart...")

    stop_event = driver_ref.get("stop_event")
    listener = driver_ref.get("listener")
    
    if stop_event is not None:
        stop_event.set()

    if listener is not None:
        listener.join(timeout=3)
        
    driver_ref["restart"] = True

    driver = driver_ref.get("driver")

    cleanup_driver(driver=driver, driver_path=None)


parser = argparse.ArgumentParser(description="Visit AdURLs")
parser.add_argument("--config",required=True)


args = parser.parse_args()

with open(args.config, "r", encoding="utf-8") as f:
    config = json.load(f)

country = config["country"]
autorun = config["autorun"]
autorun_start = config["auto_start"]
page_load_strategy = config["loadMode"]
headless = config["headless"]
platform_configs = config["platforms"]

print(f"[INFO] Running visit Ads URLs for country: {country}")


date_str = datetime.now().strftime("%d%m")
base_dir = "capturesGeneralURL"
idDir = getidDir(base_dir, country, date_str)


BASE_DIR = Path(__file__).resolve().parent


ip=""

if page_load_strategy in ["none", "eager"]:
    timewait = 20
else:
    timewait = 5

def work_once(choice_banner, run_no, listSites, platform_name, siteRestore, restoreSession, outdir, err=False):
    driver = None
    for attemp in range(3):
        try:
            driver = init_browser(headless=headless, version_main=153, page_load_strategy=page_load_strategy)
            break
        except Exception as e:
            print(f"Error in create driver: {e} \nTry again")
            time.sleep(5)
            
    if driver is None:
        raise RuntimeError("Cannot create driver")
    
    print(f"[INFO] Browser driver created.")

    driver_ref = {"driver": driver, "done": False, "restart": False, "stop_event": None, "listener": None}

    listError = []
    idError = set()

    for idx, site in enumerate(listSites, start=1):
        _erMessage = ""
        print(
            f"[INFO] Site {idx}/{len(listSites)} "
            f"(id_csv={site['id_site']}): {site['url']}"
        )

        id_csv = site['id_site']
        url = site['url']

        driver_ref["restart"] = False
        driver_ref["done"] = False
        driver_ref["stop_event"] = None
        driver_ref["listener"] = None

        watchdog_thread = threading.Thread(target=watchdog, args=(driver_ref,id_csv))
        watchdog_thread.start()

        with get_db_conn(country, choice_banner) as conn:
            id_site = insert_site_GeneralAds(conn, domain_url = url, id_csv=id_csv, ip=ip, country=country, run_no=run_no, platform=platform_name, status="error")

        url_reached = ""

        try:
            driver.get("about:blank")
            clear_all_storage(driver)
            print("Cleared cookie & cache!")

            if siteRestore is not None:
                driver.get(siteRestore)
                if platform_name == "FB":
                    click_FB_accept_button(driver)
                if platform_name == "TT":
                    click_TT_accept_button(driver)
                if platform_name == "TW":
                    click_TW_accept_button(driver)
                
                time.sleep(timewait)
                importDataVisit(driver, restoreSession)

            time.sleep(timewait)

            print("==============="*3)
            dir_bc = "/bannerclick/" + str(id_site) + "/"
            outdir_bc = "./" + outdir + dir_bc
            print(f"Running for site: {id_csv}")
            has_banner = bc.run_ONE_pc_General(driver = driver, driver_ref=driver_ref, choice = choice_banner, url=url, headless=headless, dir_bc = outdir_bc, id_site=id_site, id_csv=id_csv, country=country, run_no=run_no, platform=platform_name)
            time.sleep(6)
            url_reached = driver.current_url

            with get_db_conn(country, choice_banner) as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE sites SET reached_url=%s, crawl_status='success' WHERE id_site=%s""", (url_reached, id_site))

            driver_ref["done"] = True
        except WebDriverException as e:
            _erMessage = f"WebDriver Error: {e}"
            print(_erMessage)
            with get_db_conn(country, choice_banner) as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE sites SET crawl_status='error', error_message=%s WHERE id_site=%s""", (_erMessage, id_site))

            if "ERR_NAME_NOT_RESOLVED" in str(e) or "ERR_CONNECTION_CLOSED" in str(e):
                if err==False and site['id_site'] not in idError:
                    site_err = {"id_site": site['id_site'], "url": site['url']}
                    listError.append(site_err)
                    idError.add(site['id_site'])

                stop_event = driver_ref.get("stop_event")
                listener = driver_ref.get("listener")
                if stop_event is not None:
                    stop_event.set()
                if listener is not None:
                    listener.join(timeout=3)

                driver_ref["done"] = True


            else:
                driver_ref["restart"] = True

        except Exception as e:
            _erMessage = f"Error: {e}"
            with get_db_conn(country, choice_banner) as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE sites SET crawl_status='error', error_message=%s WHERE id_site=%s""", (_erMessage, id_site))

            if "Max retries exceeded" in str(e):
            #if "Read timed out" in str(e) or "Max retries exceeded" in str(e):
                if err==False and site['id_site'] not in idError:
                    site_err = {"id_site": site['id_site'], "url": site['url']}
                    listError.append(site_err)
                    idError.add(site['id_site'])

                stop_event = driver_ref.get("stop_event")
                listener = driver_ref.get("listener")
                if stop_event is not None:
                    stop_event.set()
                if listener is not None:
                    listener.join(timeout=3)

                driver_ref["done"] = True
            else:
                driver_ref["restart"] = True



        finally:
            driver_ref["done"] = True
    
        watchdog_thread.join()
        if driver_ref["restart"]:
            if err == False and site['id_site'] not in idError:
                site_err = {"id_site": site['id_site'], "url": site['url']}
                listError.append(site_err)
                idError.add(site['id_site'])
            print(f"[INFO] Restarting browser driver...")

            time.sleep(2)

            stop_event = driver_ref.get("stop_event")
            listener = driver_ref.get("listener")
            if stop_event is not None:
                stop_event.set()

            if listener is not None:
                listener.join(timeout=3)

            cleanup_driver(driver=driver, driver_path=None)
            driver = None
            for attemp in range(3):
                try:
                    driver = init_browser(headless=headless, version_main=153, page_load_strategy=page_load_strategy)
                    break
                except Exception as e:
                    print(f"Error in create driver: {e} \nTry again")
                    time.sleep(5)

            if driver is None:
                raise RuntimeError("Cannot create driver!")

            print(f"[INFO] Browser driver created.")
            driver_ref["driver"] = driver
            
                   
        time.sleep(5)  # Brief pause between sites

    else:
        print("[INFO] All Ads URL processed.")
        time.sleep(10)
        cleanup_driver(driver=driver,driver_path=None)

    if len(listError)>0 and err==False:
        print(f"[ERROR-RUN] Choice {choice_banner} - Run {run_no}: {len(listError)} sites failed due to connection issues. Try again....")
        work_once(choice_banner, run_no, listError, platform_name, siteRestore, restoreSession, outdir, err=True)

if autorun != 0:
    if autorun_start != 0:
        start_run = autorun_start
        autorun = autorun + start_run -1
    else:
        start_run = 1
else:
    start_run = 1
    autorun = 1

for platform_name in PLATFORMS:
    platform_config = platform_configs[platform_name]
    sites_path = platform_config["sites"]
    begin = platform_config["begin"]
    end = platform_config["end"]
    siteRestore = platform_config["siteRestore"]
    restoreSession = platform_config["restoreSession"]

    print(f"RUN FOR PLATFORM {platform_name}")
    _outdir = getOutDir(platform_name)


    listSites = loadSitesFromCSV(sites_path)
    total_sites = len(listSites)


    if begin is None and end is None:
        selected_sites = listSites
    elif begin is not None and end is None:
        selected_sites = listSites[begin:]
    elif begin is None and end is not None:
        selected_sites = listSites[:end]
    else:
        selected_sites = listSites[begin:end]

    print(
        f"[INFO] Loaded {total_sites} urls, "
        f"processing {len(selected_sites)} urls "
        f"(begin={begin}, end={end})"
    )

    for choice in CHOICES:
        for i in range(start_run, autorun + 1):
            print(f"Start choice {choice} - run no {i}.")
            work_once(choice, i, selected_sites, platform_name, siteRestore, restoreSession, _outdir)
            print(f"Finished run no {i}. Sleep 40s")
            time.sleep(30)

cleanup_driver(driver=None, driver_path=None)