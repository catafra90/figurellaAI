# File: app/clients/utils.py

import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


def scrape_all_clients():
    """
    Log into the Figurella dashboard, scrape all clients across all pages,
    and return a list of dicts. No Excel is written.
    """
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Optional: run headless
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)
    all_rows = []

    try:
        # ─── LOGIN ──────────────────────────────────────────────────
        driver.get("https://newton.hosting.memetic.it/login")
        wait.until(EC.presence_of_element_located((By.ID, "txtUsername"))).send_keys("Tutor")
        wait.until(EC.presence_of_element_located((By.ID, "txtPassword"))).send_keys("FiguMass2025$")
        wait.until(EC.element_to_be_clickable((By.ID, "btnAccedi"))).click()
        wait.until(EC.url_contains("/assist/client_edit"))

        # ─── SCRAPE ALL PAGES ────────────────────────────────────────
        page = 1
        while True:
            print(f"📄 Scraping page {page}…")
            soup = BeautifulSoup(driver.page_source, "html.parser")
            table = soup.find("table", {"id": "ctl00_cphMain_gvMain"})
            if not table:
                break

            for tr in table.find_all("tr")[1:-1]:
                cols = tr.find_all("td")
                if len(cols) < 5:
                    continue

                # Name
                raw = cols[1].get_text(" ", strip=True).split()
                last = raw[0] if raw else ""
                first = " ".join(raw[1:]) if len(raw) > 1 else ""

                # Contact
                email_tag = cols[2].find("a", href=lambda x: x and "mailto:" in x)
                email = email_tag.get_text(strip=True) if email_tag else ""
                phone = cols[2].get_text(" ", strip=True).replace(email, "").strip()

                # Date & Status
                date_txt = cols[4].get_text(strip=True)
                status_tag = cols[4].find("span")
                status = status_tag.get_text(strip=True) if status_tag else ""
                date = date_txt.replace(status, "").strip() if status else date_txt

                all_rows.append({
                    "Name": f"{first} {last}".strip(),
                    "Email": email,
                    "Phone": phone,
                    "Date Created": date,
                    "Status": status
                })

            # Next page
            next_link = None
            for a in soup.select("a[href*='Page$']"):
                if f"Page${page+1}" in a["href"]:
                    next_link = a
                    break
            if not next_link:
                break

            tgt, arg = next_link["href"].split("'")[1::2]
            xpath = f"//a[contains(@href, \"__doPostBack('{tgt}','{arg}')\")]"
            elem = driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].click();", elem)
            page += 1
            time.sleep(2)

    finally:
        driver.quit()

    return all_rows


# File: app/clients/routes.py

import pandas as pd
from flask import Blueprint, render_template, redirect, url_for, flash
from app import db
from app.models import Client
from .utils import scrape_all_clients

clients_bp = Blueprint('clients', __name__, template_folder='templates')

@clients_bp.route('/clients')
def clients():
    """Display all clients from the database including date and status."""
    clients = Client.query.order_by(Client.name).all()
    data = [
        {
            'Name':   c.name,
            'Date Created': c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
            'Status': c.status or '',
            'Email':  c.email or '',
            'Phone':  c.phone or ''
        }
        for c in clients
    ]

    columns = ['Name', 'Date Created', 'Status', 'Email', 'Phone']
    df = pd.DataFrame(data, columns=columns)

    table_html = df.to_html(
        table_id='clients-table',
        classes='min-w-full text-sm text-left table-auto display',
        index=False,
        border=0
    )

    return render_template(
        'clients_table.html',
        clients_table=table_html,
        active_page='clients'
    )

@clients_bp.route('/refresh_clients')
def refresh_clients():
    """Scrape and upsert clients into the DB—no Excel involved."""
    try:
        rows = scrape_all_clients()
    except Exception as e:
        flash(f"Error scraping clients: {e}", 'error')
        return redirect(url_for('clients.clients'))

    inserted = 0
    for row in rows:
        name = row.get('Name')
        if not name:
            continue
        client = Client.query.filter_by(name=name, email=row.get('Email')).first()
        if not client:
            client = Client(
                name=name,
                email=row.get('Email'),
                phone=row.get('Phone'),
                status=row.get('Status')
            )
            db.session.add(client)
            inserted += 1
        else:
            client.phone  = row.get('Phone')
            client.status = row.get('Status')

    db.session.commit()
    flash(f"Clients synced! ({inserted} new added)", 'success')
    return redirect(url_for('clients.clients'))
