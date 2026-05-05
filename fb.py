import time
import re
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


def setup_driver():
    chrome_options = Options()
    # Cấu hình bắt buộc để chạy trên Streamlit Cloud (Linux)
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    # Giảm dấu vết bot
    chrome_options.add_argument(
        "--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--lang=vi")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # Khởi tạo driver từ binary của hệ thống (đã cài qua packages.txt)
    driver = webdriver.Chrome(options=chrome_options)
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
    # Khởi tạo driver một lần duy nhất
    driver = setup_driver()
    results = []

    # Xpath cho Like/Cmt dựa trên cấu trúc Facebook
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
            time.sleep(5)  # Đợi load
            close_popups(driver)

            try:
                view_el = driver.find_element(By.CLASS_NAME, "_26fq")
                data["views"] = view_el.text.strip()
            except:
                pass

            # --- PHẦN 2: LẤY LIKE/CMT/SHARE ---
            reel_url = f"https://www.facebook.com/reels/{video_id}/"
            driver.get(reel_url)
            time.sleep(5)
            close_popups(driver)

            # Lấy Like & Comment (Pseudo Content)
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

            # Lấy Share
            try:
                share_div = driver.find_element(
                    By.XPATH, "//div[@aria-label='Chia sẻ' or @aria-label='Share']")
                share_text = share_div.text.strip()
                if not share_text:
                    share_text = share_div.find_element(
                        By.TAG_NAME, "span").text.strip()
                data["shares"] = share_text if share_text else "0"
            except:
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
