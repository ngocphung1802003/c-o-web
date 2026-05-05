import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--lang=vi")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)


def get_id(url):
    match = re.search(r'(?:v=|/reels?/|/videos/|v/|v=)(\d+)', url)
    return match.group(1) if match else None


def get_pseudo_content(driver, element, pseudo_type="before"):
    js = f"return window.getComputedStyle(arguments[0], '::{pseudo_type}').getPropertyValue('content');"
    content = driver.execute_script(js, element)
    if content and content not in ['none', 'normal']:
        return content.replace('"', '').replace("'", "").strip()
    return ""


def close_popups(driver):
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        driver.execute_script("""
            var closeBtn = document.querySelector('div[aria-label="Đóng"], div[aria-label="Close"], div[role="dialog"] div[role="button"]');
            if(closeBtn) closeBtn.click();
        """)
    except:
        pass


def scrape_facebook_full_stats(urls):
    driver = setup_driver()
    results = []

    # Xpath cho Like/Cmt từ code cũ (Pseudo class)
    xpath_stats = "//span[contains(@class, 'x1lliihq') and contains(@class, 'x6ikm8r') and contains(@class, 'xuxw1ft')]"

    for i, original_url in enumerate(urls):
        video_id = get_id(original_url)
        if not video_id:
            continue

        print(f"[{i+1}/{len(urls)}] Đang xử lý ID: {video_id}")
        data = {"url": original_url, "views": "N/A",
                "likes": "0", "comments": "0", "shares": "0"}

        try:
            # --- PHẦN 1: LẤY VIEW (DÙNG /WATCH/) ---
            watch_url = f"https://www.facebook.com/watch/?v={video_id}"
            driver.get(watch_url)
            time.sleep(6)
            close_popups(driver)
            try:
                view_el = driver.find_element(By.CLASS_NAME, "_26fq")
                data["views"] = view_el.text.strip()
            except:
                pass

            # --- PHẦN 2: LẤY LIKE/CMT/SHARE (DÙNG /REEL/) ---
            reel_url = f"https://www.facebook.com/reels/{video_id}/"
            driver.get(reel_url)
            time.sleep(6)
            close_popups(driver)

            # 2.1. Lấy Like & Comment bằng cơ chế Pseudo
            stat_elements = driver.find_elements(By.XPATH, xpath_stats)
            temp_stats = []
            for el in stat_elements:
                v_real = el.text.strip()
                v_before = get_pseudo_content(driver, el, "before")
                v_after = get_pseudo_content(driver, el, "after")
                combined = (v_before + v_real + v_after).strip()
                if any(char.isdigit() for char in combined):
                    temp_stats.append(combined)

            if len(temp_stats) >= 1:
                data["likes"] = temp_stats[0]
            if len(temp_stats) >= 2:
                data["comments"] = temp_stats[1]

            # 2.2. Lấy Share bằng cách nhắm trực tiếp vào div aria-label="Chia sẻ"
            try:
                share_div = driver.find_element(
                    By.XPATH, "//div[@aria-label='Chia sẻ' or @aria-label='Share']")
                # Lấy text trực tiếp hoặc từ span con bên trong
                share_text = share_div.text.strip()
                if not share_text:
                    # Nếu text trống, thử tìm span con
                    try:
                        share_text = share_div.find_element(
                            By.TAG_NAME, "span").text.strip()
                    except:
                        pass

                data["shares"] = share_text if share_text else "0"
            except:
                data["shares"] = "0"

            print(
                f"   > {data['views']} | {data['likes']} Like | {data['comments']} Cmt | {data['shares']} Share")
            results.append(data)

        except Exception as e:
            print(f"   > Lỗi: {e}")
            results.append(data)

    driver.quit()
    return results


if __name__ == "__main__":
    input_urls = [
        "https://www.facebook.com/watch/?v=1270887347800010",
        "https://www.facebook.com/reel/1299971728731776"
    ]

    final_output = scrape_facebook_full_stats(input_urls)

    print("\n" + "="*100)
    print(f"{'VIEWS':<15} | {'LIKE':<10} | {'CMT':<10} | {'SHARE':<10} | {'LINK'}")
    print("-" * 100)
    for r in final_output:
        print(
            f"{r['views']:<15} | {r['likes']:<10} | {r['comments']:<10} | {r['shares']:<10} | {r['url']}")
