import json

def exportData(driver, output_file="fb_session.json"):
    local_storage = driver.execute_script("""
        var items = {};
        for (var i = 0; i < localStorage.length; i++) {
            var k = localStorage.key(i);
            items[k] = localStorage.getItem(k);
        }
        return items;
    """)

    cookies = driver.get_cookies()

    session_storage = driver.execute_script("""
        var items = {};
        for (var i = 0; i < sessionStorage.length; i++) {
            var k = sessionStorage.key(i);
            items[k] = sessionStorage.getItem(k);
        }
    return items;
    """)

    data = {
        "cookies": cookies,
        "local_storage": local_storage,
        "session_storage": session_storage,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_file}")




def importData(driver, input_file="fb_session.json"):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Cookies
    for cookie in data["cookies"]:
        cookie = cookie.copy()
        cookie.pop("sameSite", None)

        try:
            driver.add_cookie(cookie)
        except Exception as e:
            print("Pass - Import cookie error:", cookie.get("name"), e)
            pass

    # LocalStorage
    driver.execute_script("localStorage.clear();")
    for k, v in data["local_storage"].items():
        try:
            driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);",k,v)
        except Exception as e:
            print("Pass - Import localStorage error:", k, e)
            pass

    # SessionStorage
    driver.execute_script("sessionStorage.clear();")
    for k, v in data["session_storage"].items():
        try:
            driver.execute_script("sessionStorage.setItem(arguments[0], arguments[1]);",k,v)
        except Exception as e:
            print("Pass - Import sessionStorage error:", k, e)
            pass

    url = driver.current_url
    if "tiktok.com" in url:
        driver.get("https://www.tiktok.com/")
    else:
        driver.refresh()


def importDataVisit(driver, input_file):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Cookies
    for cookie in data["cookies"]:
        cookie = cookie.copy()
        cookie.pop("sameSite", None)

        try:
            driver.add_cookie(cookie)
        except Exception as e:
            print("Import cookie error:", cookie.get("name"), e)
            raise



    # LocalStorage
    driver.execute_script("localStorage.clear();")
    for k, v in data["local_storage"].items():
        try:
            driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);",k,v)
        except Exception as e:
            print("Import localStorage error:", k, e)
            raise

    # SessionStorage
    driver.execute_script("sessionStorage.clear();")
    for k, v in data["session_storage"].items():
        try:
            driver.execute_script("sessionStorage.setItem(arguments[0], arguments[1]);",k,v)
        except Exception as e:
            print("Import sessionStorage error:", k, e)
            raise

    driver.refresh()
    # url = driver.current_url
    # if "tiktok.com" in url:
    #     driver.get("https://www.tiktok.com/")
    # else:
    #     driver.refresh()

