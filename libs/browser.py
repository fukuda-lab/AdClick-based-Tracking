import undetected_chromedriver as uc
import os
import time
from libs.cleanup import cleanup_driver



def safe_get(driver, url, timeout=20):
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
    except:
        driver.execute_script("window.stop();")
        pass


# --- Start Chrome with devtools logging enabled ---
def init_browser(user_data_dir = None, headless=False, extension_unpacked_folder=None, chromeDriverPath=None, binary_location=None, version_main=151, page_load_strategy="normal"):
    Try_Attemp = 30
    for attempt in range(Try_Attemp):
        driver = None
        
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run --no-service-autorun --password-store=basic")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--start-maximized")
        options.page_load_strategy = page_load_strategy

        if binary_location:
            options.binary_location = binary_location


        if user_data_dir:
            options.add_argument(f"--user-data-dir={user_data_dir}")

        if headless:
            options.add_argument("--headless=new")
    
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})  # capture network

        # Load extension
        if extension_unpacked_folder:
            if not os.path.isdir(extension_unpacked_folder):
                print(f"Unpacked extension folder not found: {extension_unpacked_folder}")
            else:
                options.add_argument('--disable-features=DisableDisableExtensionsExceptCommandLineSwitch,DisableLoadExtensionCommandLineSwitch')
                options.add_argument(f'--load-extension={extension_unpacked_folder}')
                options.add_argument(f'--disable-extensions-except={extension_unpacked_folder}')
                print(f"Loaded unpacked extension from: {extension_unpacked_folder}")    
    
        # Extra flags to avoid blocking MV3 service worker
        options.add_argument("--allow-file-access-from-files")
        options.add_argument("--allow-file-access")
        options.add_argument("--enable-features=AllowServiceWorkerForClientOnIdle")

        # Avoid detection (optional)
        options.add_argument("--disable-blink-features=AutomationControlled")

        try:
            if chromeDriverPath:
                driver = uc.Chrome(driver_executable_path=chromeDriverPath,version_main=version_main,options=options,headless=headless)
            else:
                driver = uc.Chrome(options=options,headless=headless,version_main=version_main)

            time.sleep(2)
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Page.enable", {})
            driver.command_executor.client_config.timeout = 1000

            return driver

        except Exception as e:
            print(f"Attempt {attempt + 1}/{Try_Attemp} failed")
            cleanup_driver(driver=driver, driver_path=None)
            
            time.sleep(10)

    raise RuntimeError(f"Failed to create Chrome driver after {Try_Attemp} attempts")


def get_installed_extension_ids(user_data_dir):
    import json
    prefs_path = os.path.join(user_data_dir, "Default", "Preferences")

    if not os.path.isfile(prefs_path):
        raise FileNotFoundError("Chrome Preferences file not found! Did you use --user-data-dir?")

    with open(prefs_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    settings = data.get("extensions", {}).get("settings", {})

    extensions = []
    for ext_id, info in settings.items():
        ext_name = info.get("manifest", {}).get("name", "Unknown")
        ext_version = info.get("manifest", {}).get("version", "")
        extensions.append({"id": ext_id,"name": ext_name,"version": ext_version})

    return extensions



def kill_chrome_processes(profile_dir):
    import psutil
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = " ".join(proc.info['cmdline']).lower()
            if profile_dir.lower() in cmd:
                proc.kill()
        except:
            pass

def close_and_delete_profile(driver, profile_dir):
    import time, shutil, os
    try:
        driver.quit()
    except:
        pass
    
    time.sleep(2)
    kill_chrome_processes(profile_dir)

    # Wait a bit for processes to fully exit
    time.sleep(1)

    # Attempt to remove multiple times
    for _ in range(5):
        try:
            shutil.rmtree(profile_dir)
            print("Deleted:", profile_dir)
            return
        except Exception as e:
            print("Retry delete:", e)
            time.sleep(0.5)

    print("Failed to delete profile:", profile_dir)



def delete_profile(profile_dir, driver_path):
    import time, shutil
    
    # Kill any remaining Chrome processes using this profile
    kill_chrome_processes(profile_dir)

    # Wait a bit for processes to fully exit
    time.sleep(1)

    # Attempt to remove multiple times
    for _ in range(5):
        try:
            shutil.rmtree(profile_dir)
            print("Deleted:", profile_dir)
            return
        except Exception as e:
            print("Retry delete:", e)
            time.sleep(0.5)

    print("Failed to delete profile:", profile_dir)

    if driver_path is not None:
        try:
            os.remove(driver_path)
        except:
            pass
