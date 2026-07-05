import os
import time
import re
import shutil
import subprocess
import streamlit as st

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


def setup_driver():
    options = Options()

    # Headless mới (ổn định hơn headless cũ trên Linux/Docker)
    options.add_argument("--headless=new")

    # Các flag quan trọng cho môi trường container / server không có GUI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-software-rasterizer")

    # Bỏ --remote-debugging-port=9222 cố định vì có thể gây xung đột cổng
    # khi Streamlit rerun script và driver cũ chưa kịp quit(), khiến Chrome
    # crash ngay khi khởi động (đúng lỗi "Chrome instance exited" bạn gặp).
    # Nếu vẫn cần debug port, dùng cổng 0 để hệ thống tự cấp phát ngẫu nhiên:
    # options.add_argument("--remote-debugging-port=0")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    chromium_path = (
        shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
        or "/usr/bin/chromium"
    )
    driver_path = (
        shutil.which("chromedriver")
        or shutil.which("chromium-driver")
        or "/usr/bin/chromedriver"
    )

    # --- DEBUG: hiển thị đường dẫn thực tế để kiểm tra môi trường ---
    st.caption(
        f"🔧 Chromium: `{chromium_path}` | tồn tại: {os.path.exists(chromium_path)}")
    st.caption(
        f"🔧 Chromedriver: `{driver_path}` | tồn tại: {os.path.exists(driver_path)}")

    if not os.path.exists(chromium_path) or not os.path.exists(driver_path):
        raise FileNotFoundError(
            "Không tìm thấy chromium hoặc chromedriver trên hệ thống. "
            "Hãy kiểm tra file packages.txt (nếu dùng Streamlit Community Cloud) "
            "cần có 2 dòng: 'chromium' và 'chromium-driver'."
        )

    options.binary_location = chromium_path

    # log_output=subprocess.STDOUT giúp in ra lý do Chrome crash thật sự
    # (ví dụ thiếu shared library, hết bộ nhớ, v.v.) ra terminal/log server.
    service = Service(driver_path, log_output=subprocess.STDOUT)

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        # Nếu vẫn crash, thử lại với --single-process (cứu cánh cho môi
        # trường container ít RAM, ví dụ Streamlit Community Cloud 1GB RAM).
        st.warning(
            f"Lần thử đầu tiên thất bại ({e}). Đang thử lại với chế độ single-process...")
        options.add_argument("--single-process")
        service = Service(driver_path, log_output=subprocess.STDOUT)
        driver = webdriver.Chrome(service=service, options=options)

    return driver


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
    except Exception:
        pass


def scrape_facebook_full_stats(urls):
    driver = setup_driver()
    results = []

    xpath_stats = "//span[contains(@class, 'x1lliihq') and contains(@class, 'x6ikm8r') and contains(@class, 'xuxw1ft')]"

    try:
        for i, original_url in enumerate(urls):
            video_id = get_id(original_url)
            if not video_id:
                continue

            st.write(f"🔍 Đang xử lý [{i+1}/{len(urls)}]: ID {video_id}")
            data = {"url": original_url, "views": "N/A",
                    "likes": "0", "comments": "0", "shares": "0"}

            try:
                # --- PHẦN 1: LẤY VIEW (DÙNG /WATCH/) ---
                watch_url = f"https://www.facebook.com/watch/?v={video_id}"
                driver.get(watch_url)

                time.sleep(1)
                close_popups(driver)

                try:
                    view_el = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CLASS_NAME, "_26fq"))
                    )
                    data["views"] = view_el.text.strip()
                except TimeoutException:
                    pass

                # --- PHẦN 2: LẤY LIKE/CMT/SHARE ---
                reel_url = f"https://www.facebook.com/reels/{video_id}/"
                driver.get(reel_url)

                time.sleep(1)
                close_popups(driver)

                try:
                    stat_elements = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located(
                            (By.XPATH, xpath_stats))
                    )

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
                except TimeoutException:
                    pass

                try:
                    share_div = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//div[@aria-label='Chia sẻ' or @aria-label='Share']"))
                    )
                    share_text = share_div.text.strip()
                    if not share_text:
                        share_text = share_div.find_element(
                            By.TAG_NAME, "span").text.strip()
                    data["shares"] = share_text if share_text else "0"
                except (TimeoutException, Exception):
                    pass

                results.append(data)

            except Exception as e:
                st.error(f"Lỗi khi cào URL {original_url}: {e}")
                results.append(data)
    finally:
        driver.quit()

    return results


if __name__ == "__main__":
    st.set_page_config(page_title="FB Scraper", layout="wide")
    st.title("🚀 Facebook Video/Reel Scraper")

    input_text = st.text_area(
        "Nhập danh sách link Facebook (mỗi link một dòng):",
        height=150,
        value="https://www.facebook.com/watch/?v=1270887347800010",
    )

    if st.button("Bắt đầu cào dữ liệu"):
        urls = [url.strip() for url in input_text.split("\n") if url.strip()]
        if urls:
            with st.spinner('Đang khởi động trình duyệt ẩn và cào dữ liệu...'):
                try:
                    final_output = scrape_facebook_full_stats(urls)
                    st.success("Hoàn thành!")
                    st.table(final_output)
                except FileNotFoundError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Không thể khởi động trình duyệt: {e}")
        else:
            st.warning("Vui lòng nhập ít nhất một link.")
