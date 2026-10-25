import time
from selenium.webdriver.common.by import By
import argparse
from libs.backupSession import importData, exportData
from libs.helpers import unzip_profile
from libs.cleanup import cleanup_driver
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pathlib import Path
import shutil
from libs.process import create_only_driver

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
    #input("Press Enter to continue")

def parse_args():
    parser = argparse.ArgumentParser(description="Crawl Facebook AdURLs")
    parser.add_argument("--profile-zip", help="Name of the Chrome profile ZIP file to use. The file must exist inside the default 'profiles/' directory. ")
    parser.add_argument("--restoreSession", help="JSON session restore")
    parser.add_argument("--timeoutMins", type=int, default=5, help="Page visit (mins). Default: 5 mins")
    parser.add_argument("--pause", type=int, default=20, help="Pause time per scroll (seconds). Default: 20 secs")
    parser.add_argument("--round", type=int, default=1, help="Num of round")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--country", required=True, help="Country code")
    parser.add_argument("--autoRun", type=int, default=1, help="Run auto (default: 1)")
    
    return parser.parse_args()

def collect_ad_urls(driver):
    urls = set()
    sponsored_keywords = ["Sponsored"]
    posts = driver.find_elements(By.XPATH, "//div[@role='feed']//div[@data-pagelet]")

    for post in posts:
        try:
            post_text = post.text

            is_sponsored = any(
                keyword in post_text
                for keyword in sponsored_keywords
            )

            if not is_sponsored:
                continue

            links = post.find_elements(By.TAG_NAME, "a")

            for link in links:
                href = link.get_attribute("href")

                if href and "facebook.com" in href:
                    urls.add(href)

        except Exception:
            pass

    return sorted(urls)

def getAdsHref(driver):
    urls = set()
    try:
        ads = WebDriverWait(driver, 40).until(EC.presence_of_all_elements_located((By.XPATH,'//a[contains(@href,"https://l.facebook.com/l.php")]')))
    except TimeoutError:
        ads = []

    for ad in ads:
        try:
            href = ad.get_attribute("href")
            urls.add(href)
        except StaleElementReferenceException:
            continue
        except Exception as e:
            print("Error getting href:", e)
            continue
    return urls




def test2(driver):
    ads = []
    image_blocks = driver.find_elements(By.CSS_SELECTOR,'[data-ad-rendering-role="image"]')
    for block in image_blocks:
        try:
            link = block.find_element(By.CSS_SELECTOR, 'a[href*="l.facebook.com/l.php"]')
            ads.append({"href": link.get_attribute("href"), "element": block})
        except:
            pass
    return ads

# =============================


def collect_ad_urls(driver):
    urls = set()
    #selector = """[data-ad-rendering-role="image"] a, [data-ad-rendering-role="title"] a"""
    selector = """[data-ad-rendering-role="image"] a"""

    links = driver.find_elements(By.CSS_SELECTOR, selector)

    for link in links:
        print("----")
        print(link.get_attribute("outerHTML"))
        try:
            href = link.get_attribute("href")
            if not href:
                continue
            urls.add(href)
        except Exception:
            pass
    
    return urls



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

def main():
    args = parse_args()
    profile_name = args.profile_zip
    timeoutMins = args.timeoutMins
    pause = args.pause
    round = args.round
    headless = args.headless
    country = args.country
    autoRun = args.autoRun
    restoreSession_raw = args.restoreSession
    if restoreSession_raw:
        restoreSession = f"profiles/{restoreSession_raw}"

    
    OUTPUT_CSV = f"adURLs/Facebook_AdUrl_{country}_round{round}.csv"

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
                continue

            print(f"[INFO] Browser driver created.")
            driver.get("https://www.facebook.com")
            time.sleep(5)
            click_FB_accept_button(driver)
            time.sleep(10)

            #RestoreSession
            importData(driver, restoreSession)
            print(f"[INFO] Session restored.")
            time.sleep(2)


            start = time.time()
            while (time.time() - start) < timeoutMins*60:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(pause)

                hrefs = getAdsHref(driver)
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
            print(f"[ERROR] {e}")
            time.sleep(2)
            cleanup_driver(driver=driver, driver_path=None)
            time.sleep(10)
            
        # == Quit Browser

    
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
