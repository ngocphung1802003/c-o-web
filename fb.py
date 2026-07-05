import time
import re
import streamlit as st

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def setup_driver():
    options = Options()

    # Dùng headless cơ bản (ổn định hơn trên Linux Debian)
    options.add_argument("--headless")

    # Các flag tối quan trọng
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")

    # FLAG CỨU CÁNH: Khắc phục lỗi Crash do xung đột port trên Docker/Streamlit
    options.add_argument("--remote-debugging-port=9222")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    chromium_path = shutil.which("chromium") or shutil.which(
        "chromium-browser") or "/usr/bin/chromium"
    driver_path = shutil.which("chromedriver") or shutil.which(
        "chromium-driver") or "/usr/bin/chromedriver"

    options.binary_location = chromium_path
    service = Service(driver_path)

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
        # Nhấn ESC để đóng các overlay
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        # Thực thi JS để click nút đóng nếu có
        driver.execute_script("""
            var closeBtn = document.querySelector('div[aria-label="Đóng"], div[aria-label="Close"], div[role="dialog"] div[role="button"]');
            if(closeBtn) closeBtn.click();
        """)
    except:
        pass


def scrape_facebook_full_stats(urls):
    driver = setup_driver()
    results = []

    # Xpath cho Like/Cmt
    xpath_stats = "//span[contains(@class, 'x1lliihq') and contains(@class, 'x6ikm8r') and contains(@class, 'xuxw1ft')]"

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

            # Đóng popup ngay sau khi trang bắt đầu tải
            time.sleep(1)  # Nghỉ rất ngắn để DOM khởi tạo body
            close_popups(driver)

            try:
                # Đợi tối đa 10s cho đến khi element class "_26fq" xuất hiện
                view_el = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "_26fq"))
                )
                data["views"] = view_el.text.strip()
            except TimeoutException:
                pass  # Bỏ qua nếu sau 10s không tìm thấy view

            # --- PHẦN 2: LẤY LIKE/CMT/SHARE ---
            reel_url = f"https://www.facebook.com/reels/{video_id}/"
            driver.get(reel_url)

            time.sleep(1)
            close_popups(driver)

            try:
                # Đợi tối đa 10s cho đến khi TẤT CẢ các element stats xuất hiện
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

            # Lấy Share (Dùng WebDriverWait riêng biệt để không ảnh hưởng Like/Cmt nếu Share bị thiếu)
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

    driver.quit()
    return results


# Tích hợp vào Streamlit UI
if __name__ == "__main__":
    st.set_page_config(page_title="FB Scraper", layout="wide")
    st.title("🚀 Facebook Video/Reel Scraper")

    input_text = st.text_area("Nhập danh sách link Facebook (mỗi link một dòng):",
                              height=150,
                              value="https://www.facebook.com/watch/?v=1270887347800010")

    if st.button("Bắt đầu cào dữ liệu"):
        urls = [url.strip() for url in input_text.split("\n") if url.strip()]
        if urls:
            with st.spinner('Đang khởi động trình duyệt ẩn và cào dữ liệu...'):
                final_output = scrape_facebook_full_stats(urls)
                st.success("Hoàn thành!")
                st.table(final_output)
        else:
            st.warning("Vui lòng nhập ít nhất một link.")
