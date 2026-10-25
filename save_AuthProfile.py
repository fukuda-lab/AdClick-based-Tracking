import argparse
from libs.browser import init_browser
import time
from libs.backupSession import exportData
from libs.cleanup import cleanup_driver


def getFNAME(platform, country):
    if platform == "FB":
        f_platform = "Facebook"
        site0 = "https://www.facebook.com"
    elif platform == "TW":
        f_platform = "Twitter"
        site0 = "https://www.x.com"
    elif platform == "TT":
        f_platform = "TikTok"
        site0 = "https://www.tiktok.com/@tiktok"
    else:
        f_platform = None
        site0 = None
        return

    fname_bak = f"profiles/{country}/{f_platform}_{country}.json"
    return fname_bak, site0

PLATFORMS = ["FB", "TW", "TT"]
parser = argparse.ArgumentParser(description="Backup Authentication Profile")
parser.add_argument("--country", required=True, help="Country code")
args = parser.parse_args()

country = args.country
driver_path = None
time.sleep(2)

driver = None

for platform in PLATFORMS:
    filebak, site0 = getFNAME(platform, country)
    driver = init_browser(version_main=153, chromeDriverPath=driver_path)
    print(f"Created driver for platform {platform}")
    time.sleep(5)
    driver.get(site0)
    time.sleep(5)

    print("Please login manually...")
    input("Press Enter to export data!")
    time.sleep(5)
    exportData(driver, filebak)

    cleanup_driver(driver=driver, driver_path=None)
    time.sleep(2)