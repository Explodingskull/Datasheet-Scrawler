from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import requests
from bs4 import BeautifulSoup

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run without opening browser window
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver

def scrape_datasheet_links():
    driver = setup_driver()
    url = "https://www.digikey.in/en/products/filter/batteries-rechargeable-secondary/91"
    
    try:
        # Load category page
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table#productTable"))
        )
        time.sleep(3)  # Additional wait for table rendering

        # Parse product listings
        soup = BeautifulSoup(driver.page_source, "html.parser")
        products = []
        
        for row in soup.select("table#productTable tbody tr"):
            part_cell = row.select_one("td[data-spec=manufacturerPartNumber] a")
            if part_cell:
                products.append({
                    "mfr_part": part_cell.text.strip(),
                    "detail_url": f"https://www.digikey.in{part_cell['href']}"
                })
        
        # Get PDF links from product pages
        datasheets = []
        for product in products:
            driver.get(product["detail_url"])
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='datasheet-download']"))
            )
            pdf_link = driver.find_element(By.CSS_SELECTOR, "[data-testid='datasheet-download']").get_attribute("href")
            if pdf_link.endswith(".pdf"):
                datasheets.append((product["mfr_part"], pdf_link))
            time.sleep(2)  # Be polite to Digikey's servers
        
        return datasheets
    
    finally:
        driver.quit()

def download_pdfs(datasheets):
    os.makedirs("datasheets", exist_ok=True)
    for mfr_part, pdf_url in datasheets:
        filename = f"{mfr_part.replace('/', '-').replace(' ', '_')}.pdf"
        filepath = os.path.join("datasheets", filename)
        
        print(f"Downloading {filename}...")
        response = requests.get(pdf_url, stream=True)
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"Saved to {filepath}")

if __name__ == "__main__":
    datasheets = scrape_datasheet_links()
    download_pdfs(datasheets)
