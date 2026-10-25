import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from libs.backupSession import importData, exportData
from libs.helpers import unzip_profile
from libs.cleanup import cleanup_driver

import argparse
from pathlib import Path
import shutil

from libs.process import create_only_driver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

BASE_DIR = Path(__file__).resolve().parent
POST_QUIT_WAIT_SECONDS = 10

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

def get_ads_cta_href(driver):
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR,'a[data-e2e="ttam-ads-cta"]')
    except Exception as e:
        return None
    
    if buttons:
        href = set()
        for button in buttons:
            try:
                h = button.get_attribute("href")
                if h:
                    href.add(h)
            except Exception as e:
                continue
        return href

def save_to_csv(urls, filename):
    existing_items0 = set()
    with open(filename, 'a+', encoding='utf-8') as file:
        file.seek(0)
        for line in file:
            line = line.strip()
            if line:
                existing_items0.add(line)
    
        for item in urls:
            if item not in existing_items0:
                file.write(f"{item}\n")



def parse_args():
    parser = argparse.ArgumentParser(description="Crawl TikTok AdURLs")
    parser.add_argument("--profile-zip", help="Name of the Chrome profile ZIP file to use. The file must exist inside the default 'profiles/' directory. ")
    parser.add_argument("--restoreSession", help="JSON session restore")
    parser.add_argument("--timeoutMins", type=int, required=True, help="Page visit (mins)")
    parser.add_argument("--pause", type=int, required=True, help="Pause time per scroll (seconds). Default: 20 secs")
    parser.add_argument("--round", type=int, default=1, help="Num of round")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--country", required=True, help="Country code")
    parser.add_argument("--autoRun", type=int, default=1, help="Run auto (default: 1)")

    return parser.parse_args()

def main():
    args = parse_args()
    profile_name = args.profile_zip
    timeoutMins = args.timeoutMins
    round = args.round
    headless = args.headless
    pause = args.pause
    country = args.country
    autoRun = args.autoRun
    restoreSession_raw = args.restoreSession
    if restoreSession_raw:
        restoreSession = f"profiles/{restoreSession_raw}"


    OUTPUT_CSV = f"adURLs/TiKTok_AdUrl_{country}_round{round}.csv"

    PROFILES_DIR = BASE_DIR / "profiles"


    if not profile_name.endswith(".zip"):
        profile_name += ".zip"
    
    profiles_zip = PROFILES_DIR / profile_name

    print(f"[INFO] Using profile ZIP: {profiles_zip}")
    profile_dir = unzip_profile(profiles_zip)


    for i in range(autoRun):
        try:
            driver = None
            print(f"Run no {i}")
            driver = create_only_driver(profile_dir, headless, page_load_strategy="normal")

            if driver is None:
                print("CAN NOT CREATE DRIVER! QUIT PROCESS!")
                exit()

            print(f"[INFO] Browser driver created.")
            driver.get("https://www.tiktok.com/@tiktok")
            time.sleep(20)
            click_TT_accept_button(driver)
            time.sleep(10)

            #RestoreSession
            importData(driver, restoreSession)
            print(f"[INFO] Session restored.")
            
            #Click homepage
            time.sleep(20)
            button_home = driver.find_element(By.CSS_SELECTOR, "button[aria-label='For You']")
            clickButton(driver, button_home)
            time.sleep(20)
            tout_each = 5

            start = time.time()
            while (time.time() - start) < (timeoutMins*60):
                remaining = timeoutMins * 60 - (time.time() - start)
                if remaining <= 0:
                    break

                ActionChains(driver).send_keys(Keys.ARROW_DOWN).perform()
                time.sleep(pause)
                hrefs = get_ads_cta_href(driver)
                if hrefs is not None:
                    save_to_csv(hrefs, OUTPUT_CSV)
                time.sleep(1)

            time.sleep(2)

            try:
                exportData(driver, restoreSession)
            except Exception as e:
                pass
            time.sleep(2)
            cleanup_driver(driver=driver, driver_path=None)
            time.sleep(10)
        except Exception as e:
            time.sleep(2)
            cleanup_driver(driver=driver, driver_path=None)
            time.sleep(10)
            continue
        



    cleanup_driver(driver=None, driver_path=None)
    for _ in range(5):
        try:
            shutil.rmtree(profile_dir)
            print("Deleted:", profile_dir)
            break
        except Exception as e:
            print("Retry delete:", e)
            time.sleep(0.5)
    print("[INFO] Finished.")



if __name__ == "__main__":
    main()
