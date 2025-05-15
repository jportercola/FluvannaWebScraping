# Fluvanna Meetings Page Scraper #
### Downloads PDFs for all meetings on fluvanna website, and writes content summaries to CSV

# Builds url query strings from dicts
from urllib.parse import urlencode
# Automate browser interactions
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import shutil
# Auto downloads correct version of ChromeDriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# Parse HTML to extract info
from bs4 import BeautifulSoup
# Downloads files
import requests
# Write to CSV files
import csv
# Handle file paths, delays, reg expressions
import os
import time
import re

# Folder to store downloaded PDFs
os.makedirs('downloads', exist_ok=True)

# Root page for searching meetings
base_url = "https://www.fluvannacounty.org/meetings"

# Setup Selenium WebDriver (headless mode)
options = Options()
options.add_argument("--headless") # Runs without opening visible window
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
#Locate Chrome binary and starts browser
options.binary_location = shutil.which("chrome") or shutil.which("chrome.exe") or "C:/Program Files/Google/Chrome/Application/chrome.exe"
# Installs correct Chromedriver version automatically
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Set date filters
# Currently all meetings and all departments from 2000 to 2025
# Page number for pagination
params = {
    'date_filter[value][month]': 1,
    'date_filter[value][day]': 1,
    'date_filter[value][year]': 2000,
    'date_filter_1[value][month]': 12,
    'date_filter_1[value][day]': 31,
    'date_filter_1[value][year]': 2025,
    'field_microsite_tid': 'All',
    'field_microsite_tid_1': 'All',
    'page': 0
}

results = []

while True:
    # Build full url with base and parameters
    # Loops through paginated results until no more pages
    url = f"{base_url}?{urlencode(params)}"
    print(f"\nChecking page {params['page']}...")
    driver.get(url)

    try:
        # Waits for page to load until at least one mtg item on page
        # Skips if no results
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'views-row'))
        )
    except:
        print("Timed out waiting for page to load.")
        break

    # Loads HTML into BeautifulSoup for parsing
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    meeting_nodes = soup.select('tr.odd, tr.even')  # Rows with the odd or even class in the table
    print(f"Found {len(meeting_nodes)} meeting nodes on page {params['page']}")

    if not meeting_nodes:
        print("No meeting nodes found, stopping.")
        break

    pdfs_found_this_page = 0

    for meeting in meeting_nodes:
        # Each row parsed for title, date, pdf links
        # Create dict row with that data and append to results
        title_tag = meeting.select_one('.views-field-title')
        title = title_tag.text.strip() if title_tag else "Unknown"

        date_tag = meeting.select_one('.views-field-field-calendar-date .date-display-single')
        date = date_tag.text.strip() if date_tag else "Unknown"

        links = meeting.find_all('a', href=True)
        print(f"\nMeeting: {title} on {date}")
        for link in links:
            href = link['href']
            full_url = f"https://www.fluvannacounty.org{href}" if not href.startswith("http") else href
            print(f"Found link: {link.get_text(strip=True)} -> {full_url}")

        pdf_urls = {}

        # Looks for each document type with CSS locator
        # Downloads file if PDF
        # Extracts filename and stores local name and URL in that row
        for label, selector in {
            'Agenda': '.views-field-field-agendas a[href]',
            'Package': '.views-field-field-packets a[href]',
            'Action Report': '.views-field-field-action-reports a[href]',
            'Minutes': '.views-field-field-minutes a[href]',
            'COAD Report': '.views-field-field-other-meeting-attachments a[href]'
        }.items():
            tag = meeting.select_one(selector)
            if tag:
                raw_url = tag['href']
                full_url = f"https://www.fluvannacounty.org{raw_url}" if not raw_url.startswith('http') else raw_url
                try:
                    response = requests.get(full_url, stream=True, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/pdf' in content_type:
                        pdf_urls[label] = full_url
                    response.close()
                except Exception as e:
                    print(f"GET request failed for {full_url}: {e}")

        for pdf_type, pdf_url in pdf_urls.items():
            pdf_name = re.sub(r'[\\/*?:"<>|]', "_", pdf_url.split('/')[-1])
            local_path = os.path.join('downloads', pdf_name)

            try:
                pdf_data = requests.get(pdf_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                pdf_data.raise_for_status()
                with open(local_path, 'wb') as f:
                    f.write(pdf_data.content)
                print(f"Downloaded {pdf_name}")
                results.append({
                    'title': title,
                    'date': date,
                    'pdf_url': pdf_url,
                    'file': local_path
                })
                pdfs_found_this_page += 1
            except Exception as e:
                print(f"Failed to download {pdf_url}: {e}")

        if not meeting_nodes:
            print("No meeting nodes found. Stopping.")
            break

    time.sleep(1)
    params['page'] += 1

with open('meeting_documents.csv', 'w', newline='', encoding='utf-8') as csvfile:
    # Creates CSV with one row per meeting
    fieldnames = ['title', 'date', 'pdf_url', 'file']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

print("Finished downloading and logging PDFs.")

# Close headless browser
driver.quit()
