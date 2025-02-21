import time
import random
import string
import re
import os
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -------------------------
# Utility Functions
# -------------------------
def generate_session_id(length=10):
    """Generate a random session ID consisting of lowercase letters and digits."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def clean_subdistrict(subdistrict):
    """
    Clean the subdistrict string to generate a URL-friendly slug.
    Any sequence of non-alphanumeric characters is replaced by a hyphen.
    The result is lowercased and stripped of extra hyphens.
    """
    cleaned = re.sub(r'[^A-Za-z0-9]+', '-', subdistrict)
    return cleaned.strip('-').lower()

def initialize_driver():
    """Initializes Microsoft Edge WebDriver with custom options including headless mode."""
    options = webdriver.EdgeOptions()
    options.add_argument("--headless")  # Enable headless mode for background execution
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    driver = webdriver.Edge(options=options)
    return driver

def scroll_down(driver, delay=5):
    """Scrolls down to the bottom of the page and waits for lazy-loaded content."""
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(delay)

def extract_data(driver, control_date_dt):
    """
    Extracts listing data from the current page.
    For each row, returns:
      [Date, Address, Price, PriceTag, Area, Ft_Price, Agency]
    Only rows with a date newer or equal to control_date_dt are kept.
    """
    data = []
    try:
        tbody = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.bx--structured-list-tbody"))
        )
        rows = tbody.find_elements(By.CSS_SELECTOR, "div.cv-structured-list-item")
        print(f"Found {len(rows)} rows on this page.")
        for row in rows:
            try:
                cells = row.find_elements(By.CSS_SELECTOR, "div.cv-structured-list-data")
                if len(cells) >= 8:
                    # Extract Date from cell 0.
                    date_text = cells[0].find_element(By.CSS_SELECTOR, "div.info-date span").text.strip()
                    # Extract Address from cell 1.
                    address = cells[1].text.strip()
                    # Extract Price from cell 3 and assign PriceTag ("S" for tranPrice, "L" for tranRent).
                    try:
                        price_text = cells[3].find_element(By.CSS_SELECTOR, "span.tranPrice").text.strip()
                        price_tag = "S"
                    except Exception:
                        price_text = cells[3].find_element(By.CSS_SELECTOR, "span.tranRent").text.strip()
                        price_tag = "L"
                    # Extract Saleable Area from cell 5.
                    area = cells[5].text.strip()
                    # Extract Unit Price from cell 6.
                    ft_price = cells[6].text.strip()
                    # Extract Agency from cell 7 (try label01 then label).
                    try:
                        agency = cells[7].find_element(By.CSS_SELECTOR, "span.label01").text.strip()
                    except Exception:
                        agency = cells[7].find_element(By.CSS_SELECTOR, "span.label").text.strip()
                    
                    # Parse the row date and skip if older than control date.
                    try:
                        row_date_dt = datetime.strptime(date_text, "%Y-%m-%d")
                    except Exception:
                        row_date_dt = None
                    if row_date_dt and row_date_dt < control_date_dt:
                        continue

                    data.append([date_text, address, price_text, price_tag, area, ft_price, agency])
                    print(f"Extracted: {date_text} | {address} | {price_text} | {price_tag} | {area} | {ft_price} | {agency}")
            except Exception as row_err:
                print("Error extracting a row:", row_err)
    except Exception as e:
        print("Error locating transaction table body:", e)
    return data

def main():
    # Base URL for the live site.
    base_url = "https://hk.centanet.com/findproperty/en/list/transaction"
    
    # Set the control date (YYYY-MM-DD); adjust this value as needed.
    control_date = "2025-02-15"
    control_date_dt = datetime.strptime(control_date, "%Y-%m-%d")
    
    # Read the area codes file (ensure the file is UTF-8 friendly).
    try:
        area_df = pd.read_excel("Centanet_Res_Area_Code.xlsx", engine="openpyxl")
    except Exception as e:
        print("Error reading Centanet_Res_Area_Code.xlsx:", e)
        return

    driver = initialize_driver()
    
    # Incremental saving: define the output file.
    file_path = f"{datetime.today().strftime('%Y-%m-%d')}_centanet_res.csv"
    # Remove existing file if exists to start fresh.
    if os.path.exists(file_path):
        os.remove(file_path)
    
    try:
        # Process each row of the area codes file.
        for idx, row in area_df.iterrows():
            region = row["Region"]
            district = row["District"]
            subdistrict = row["Subdistrict"]
            code = row["Code"]

            # Clean the subdistrict string for URL formation.
            subdistrict_part = clean_subdistrict(subdistrict)
            session_id = generate_session_id()  # Generate a new session id.
            area_url = f"{base_url}/{subdistrict_part}_19-{code}?q={session_id}"
            print(f"\nProcessing area: {subdistrict} with URL: {area_url}")

            driver.get(area_url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.bx--structured-list-tbody"))
            )
            
            area_rows = []
            current_page = 1

            while True:
                print(f"\nScraping page {current_page} for area: {subdistrict} ...")
                scroll_down(driver, delay=5)
                page_data = extract_data(driver, control_date_dt)
                for d in page_data:
                    # Append area info along with the constructed area URL.
                    area_rows.append(d + [region, district, subdistrict, code, area_url])
                if not page_data:  # No new data on this page; assume done.
                    break
                try:
                    next_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-next:not([disabled])"))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(5)
                    current_page += 1
                except Exception as e:
                    print("No more pages or next page button not clickable; moving to next area:", e)
                    break
            
            print(f"Finished area: {subdistrict} after {current_page} pages; rows found: {len(area_rows)}")
            if area_rows:
                df = pd.DataFrame(area_rows,
                                  columns=["Date", "Address", "Price", "PriceTag", "Area", "Ft_Price", "Agency",
                                           "Region", "District", "Subdistrict", "Code", "Area_URL"])
                # Incremental save: append to CSV file.
                df.to_csv(file_path, mode="a", index=False, header=not os.path.exists(file_path), encoding="utf-8-sig")
                print(f"Data for area '{subdistrict}' saved (appended to {file_path}).")
            else:
                print(f"No data extracted for area: {subdistrict}")
            driver.delete_all_cookies()
            time.sleep(3)
    finally:
        driver.quit()
        print("Scraping complete.")

if __name__ == "__main__":
    main()
