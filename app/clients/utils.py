import os
import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

def scrape_all_clients():
    chrome_options = Options()
    # chrome_options.add_argument("--headless=new")  # Enable headless if desired
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)

    try:
        print("Opening login page...")
        driver.get("https://newton.hosting.memetic.it/login")
        wait.until(EC.presence_of_element_located((By.ID, "txtUsername"))).send_keys("Tutor")
        wait.until(EC.presence_of_element_located((By.ID, "txtPassword"))).send_keys("FiguMass2025$")
        wait.until(EC.element_to_be_clickable((By.ID, "btnAccedi"))).click()

        print("Logging in...")
        wait.until(EC.url_contains("/assist/client_edit"))
        print("Login successful. Waiting to observe page...")

        all_rows = []
        page_counter = 1

        while True:
            print(f"📄 Scraping page {page_counter}...")
            soup = BeautifulSoup(driver.page_source, "html.parser")
            table = soup.find("table", {"id": "ctl00_cphMain_gvMain"})
            if not table:
                print("❌ Client table not found.")
                break

            rows = table.find_all("tr")[1:-1]
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 5:
                    continue

                # 🧑 Name Split: LastName FirstName
                raw_name = cols[1].get_text(separator=" ", strip=True)
                split_name = raw_name.split()
                if len(split_name) >= 2:
                    last_name = split_name[0].strip()
                    first_name = " ".join(split_name[1:]).strip()
                else:
                    last_name = split_name[0].strip() if split_name else ""
                    first_name = ""

                # ✉️ Email and 📞 Phone
                email = ""
                phone = ""
                email_link = cols[2].find("a", href=lambda x: x and "mailto:" in x)
                if email_link:
                    email = email_link.get_text(strip=True)

                contact_text = cols[2].get_text(separator=" ", strip=True)
                if email:
                    contact_text = contact_text.replace(email, "")
                phone = contact_text.strip()

                # 📅 Date and Status
                date_text = cols[4].get_text(strip=True)
                status_span = cols[4].find("span")
                status = status_span.get_text(strip=True) if status_span else ""
                date_only = date_text.replace(status, "").strip() if status else date_text.strip()

                all_rows.append({
                    "First Name": first_name,
                    "Last Name": last_name,
                    "Email": email,
                    "Phone": phone,
                    "Date Created": date_only,
                    "Status": status
                })

            # ➡️ Pagination
            next_link = None
            for link in soup.find_all("a", href=True):
                if f"Page${page_counter + 1}" in link["href"]:
                    next_link = link
                    break

            if not next_link:
                print("✅ No more pages.")
                break

            try:
                event_target, event_arg = next_link["href"].split("'")[1:4:2]
                target_xpath = f"//a[contains(@href, \"__doPostBack('{event_target}','{event_arg}')\")]"
                element = driver.find_element(By.XPATH, target_xpath)
                driver.execute_script("arguments[0].click();", element)
                page_counter += 1
                time.sleep(2)
            except Exception as e:
                print("❌ Failed to click pagination link:", e)
                break

        # 💾 Save
        save_path = os.path.join(os.path.dirname(__file__), "data", "all_clients.xlsx")
        df = pd.DataFrame(all_rows)
        df.to_excel(save_path, index=False)
        print(f"✅ Saved {len(all_rows)} clients to {save_path}")

    finally:
        driver.quit()
