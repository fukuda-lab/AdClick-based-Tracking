from libs.backupSession import importData, exportData
from libs.helpers import unzip_profile
from libs.cleanup import cleanup_driver

import os
import argparse
import time
from pathlib import Path
import shutil

from libs.process import create_only_driver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import StaleElementReferenceException


from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_DIR = Path(__file__).resolve().parent
POST_QUIT_WAIT_SECONDS = 10

def clickButton(driver, btn):
    try:
        btn.click()
    except Exception as e:
        try:
            driver.execute_script("arguments[0].click();", btn)
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



def process_ad(driver, tweet):
    try:
        tweet.find_element(By.XPATH, ".//span[normalize-space()='Ad']")
    except NoSuchElementException:
        return None
    except Exception:
        return None
    
    if True:
        try:
            driver.execute_script("""arguments[0].scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});""", tweet)
            time.sleep(0.8)
        except Exception:
            return None
    try:
        card = tweet.find_element(By.CSS_SELECTOR,'[data-testid="card.wrapper"]')
        href = card.find_element(By.CSS_SELECTOR,'a[href]').get_attribute("href")
        return href

    except NoSuchElementException:
        return None
    except StaleElementReferenceException:
        return None
    except Exception:
        return None


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
            


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl Twitter AdURLs")
    parser.add_argument("--profile-zip", help="Name of the Chrome profile ZIP file to use. The file must exist inside the default 'profiles/' directory. ")
    parser.add_argument("--restoreSession", help="JSON session restore")
    parser.add_argument("--timeoutMins", type=int, default=5, help="Page visit (mins). Default: 5 mins")
    parser.add_argument("--round", type=int, default=1, help="Num of round")
    parser.add_argument("--pause", type=int, default=30, help="Pause time. Default 30s")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--country", required=True, help="Country code")
    parser.add_argument("--autoRun", type=int, default=1, help="Run auto (default: 1)")
    
    return parser.parse_args()

def main():
    args = parse_args()
    profile_name = args.profile_zip
    timeoutMins = args.timeoutMins
    round = args.round
    pause = args.pause
    headless = args.headless
    country = args.country
    autoRun = args.autoRun
    restoreSession_raw = args.restoreSession
    if restoreSession_raw:
        restoreSession = f"profiles/{restoreSession_raw}"


    OUTPUT_CSV = f"adURLs/Twitter_AdUrl_{country}_round{round}.csv"
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
            driver = create_only_driver(profile_dir, headless)

            if driver is None:
                print("CAN NOT CREATE DRIVER! QUIT PROCESS!")
                exit()

            print(f"[INFO] Browser driver created.")
            driver.get("https://x.com")
            time.sleep(5)
            click_TW_accept_button(driver)
            time.sleep(10)
    
            #RestoreSession
            importData(driver, restoreSession)
            print(f"[INFO] Session restored.")
            time.sleep(2)                
        
            start = time.time()
            while (time.time() - start) < (timeoutMins*60):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(pause)

                hrefs = set()
                tweets = driver.find_elements(By.CSS_SELECTOR,'article[data-testid="tweet"]')
                for tweet in tweets:
                    href = process_ad(driver, tweet)
                    if href:
                        hrefs.add(href)

                if hrefs:
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
