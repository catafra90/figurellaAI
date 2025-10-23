from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from openpyxl import Workbook
import os
import time

def scrape_clients():
    # Setup Chrome driver path
    chrome_driver_path = os.path.join(os.getcwd(), "chromedriver-win64", "chromedriver.exe")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Step 1: Login
        driver.get("https://newton.hosting.memetic.it/login")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtUsername"))).send_keys("Tutor")
        driver.find_element(By.ID, "txtPassword").send_keys("FiguMass2025$")
        driver.find_element(By.ID, "btnAccedi").click()

        # Step 2: Go to client page
        time.sleep(2)
        driver.get("https://newton.hosting.memetic.it/assist/client_edit")

        # Step 3: Prepare Excel data
        all_data = [["Last Name", "First Name", "Email", "Phone", "Date", "Status"]]
        page = 1

        while True:
            print(f"🔄 Scraping page {page}")
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ctl00_cphMain_gvMain")))
            rows = driver.find_elements(By.CSS_SELECTOR, "#ctl00_cphMain_gvMain tr")[1:]

            for row in rows:
                tds = row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 5:
                    continue

                # Name split
                full_name = tds[1].text.strip().split("\n")
                last_name = full_name[0] if len(full_name) > 0 else ""
                first_name = full_name[1] if len(full_name) > 1 else ""

                # Contact split
                email = ""
                phone = ""
                for a in tds[2].find_elements(By.TAG_NAME, "a"):
                    href = a.get_attribute("href") or ""
                    if href.startswith("mailto:"):
                        email = a.text.strip()
                    elif href.startswith("tel:") and a.text.strip():
                        phone = a.text.strip()

                # Date + Status
                date_parts = tds[4].text.strip().split("\n")
                date = date_parts[0] if len(date_parts) > 0 else ""
                status = date_parts[1] if len(date_parts) > 1 else ""

                all_data.append([last_name, first_name, email, phone, date, status])

            # Click next page or break
            try:
                next_button = driver.find_element(By.XPATH, f"//a[text()='{page + 1}']")
                next_button.click()
                page += 1
                time.sleep(2)
            except:
                break

        # Step 4: Save Excel file in project root
        output_path = os.path.join(os.getcwd(), "all_clients.xlsx")
        wb = Workbook()
        ws = wb.active
        for row in all_data:
            ws.append(row)
        wb.save(output_path)
        print(f"✅ Done. Saved {len(all_data) - 1} clients to all_clients.xlsx")

    finally:
        driver.quit()
