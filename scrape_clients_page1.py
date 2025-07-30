# scrape_clients_page1.py

import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

LOGIN_URL   = "https://newton.hosting.memetic.it/login"
CLIENTS_URL = "https://newton.hosting.memetic.it/assist/client_edit"
OUTPUT_FILE = "clients_page1.xlsx"

# 1) Launch Chrome & log in
opts    = webdriver.ChromeOptions()
opts.add_argument("--start-maximized")
service = Service(ChromeDriverManager().install())
driver  = webdriver.Chrome(service=service, options=opts)
wait    = WebDriverWait(driver, 15)

driver.get(LOGIN_URL)
wait.until(EC.element_to_be_clickable((By.ID, "txtUsername"))).send_keys("Tutor")
driver.find_element(By.ID, "txtPassword").send_keys("FiguMass2025$")
driver.find_element(By.ID, "btnAccedi").click()

# 2) Go to the client list & wait for the first data row
wait.until(EC.url_contains("/assist/"))
driver.get(CLIENTS_URL)
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ctl00_cphMain_gvMain tbody tr")))

# 3) Scrape only page 1
data = []
for row in driver.find_elements(By.CSS_SELECTOR, "#ctl00_cphMain_gvMain tbody tr"):
    cells = row.find_elements(By.TAG_NAME, "td")
    # skip empty or pagination rows
    if not cells or 'bs-pagination' in row.get_attribute("class"):
        continue

    status = cells[-1].text.strip()
    if "To Call" in status:
        continue

    # name in 2nd cell, edit-link ID on the <a> in 1st cell
    name     = cells[1].text.strip()
    edit_link= cells[0].find_element(By.CSS_SELECTOR, "a.btn.btn-sm")
    link_id  = edit_link.get_attribute("id")
    data.append({"Client": name, "EditLinkID": link_id})

# 4) Save to Excel
df = pd.DataFrame(data)
df.to_excel(OUTPUT_FILE, index=False)
print(f"✅ Saved {OUTPUT_FILE} ({len(df)} clients)")

driver.quit()
