import csv
import os
import requests
import tempfile
import re
import json
import pdfplumber
import pytesseract
import time
from pdf2image import convert_from_path
from fuzzywuzzy import process
import Levenshtein
import threading
import sys

class BatteryDatasheetParser:
    def __init__(self):
        self.companies = []
        self.keywords = {
            "voltage": ["nominal voltage", "rated voltage", "Vnom", "voltage"],
            "capacity": ["nominal capacity", "C-rate", "mAh", "Ah", "capacity"]
        }
        self.battery_type_map = {
            "Li-ion": "Lithium-Ion",
            "Lithium Ion": "Lithium-Ion",
            "Li Polymer": "Lithium Polymer",
            "Lithium Polymer": "Lithium Polymer",
            "LiFePO4": "Lithium Iron Phosphate",
            "NiMH": "Nickel Metal Hydride",
            "Nickel Metal": "Nickel Metal Hydride",
            "NiCd": "Nickel Cadmium",
            "Nickel Cadmium": "Nickel Cadmium",
            "VRLA": "Lead Acid (VRLA)",
            "SLA": "Sealed Lead Acid (SLA)",
            "AGM": "Sealed Lead Acid (SLA, VRLA, AGM)",
            "Lithium": "Lithium",
            "Lithium Ceramic": "Lithium Ceramic",
            "Lithium Manganese Dioxide": "Lithium Manganese Dioxide"
        }


    def extract_text(self, pdf_path):
        try:
            text_blocks = []
            ocr_text = []

            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if text:
                        text_blocks.extend(line.strip() for line in text.split('\n') if line.strip())

            images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)
            for img in images:
                ocr_result = pytesseract.image_to_string(img)
                ocr_text.extend(line.strip() for line in ocr_result.split('\n') if line.strip())

            combined_text = list(dict.fromkeys(text_blocks + ocr_text))

            return {
                "text": combined_text,
                "source": "hybrid" if ocr_text else "text-based",
                "pages": len(pdf.pages)
            }

        except Exception as e:
            raise RuntimeError(f"Extraction failed: {str(e)}")

    def process_datasheet(self, pdf_path):
        try:
            extraction_result = self.extract_text(pdf_path)
            metadata = self.parse_metadata(extraction_result["text"], pdf_path)
            return {
                "metadata": metadata,
                "text_storage": {
                    "pages": extraction_result["pages"],
                    "source_type": extraction_result["source"],
                    "content": extraction_result["text"]
                }
            }
        except Exception as e:
            return {"error": str(e), "file": pdf_path}

    def load_company_list(self, path="battery_companies_list.txt"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.companies = [line.strip() for line in f if line.strip()]
        except Exception as e:
            raise RuntimeError(f"Failed to load company list: {str(e)}")

    def clean_line(self, text):
        return re.sub(r'[^a-zA-Z0-9\s\-]', '', text).lower().strip()

    def find_company_name(self, text_blocks):
        best_match = None
        best_score = 0

        for line in text_blocks:
            line_clean = self.clean_line(line)
            line_words = line_clean.split()

            for company in self.companies:
                company_clean = self.clean_line(company)

                if company_clean in line_clean:
                    return company

                company_first_word = company_clean.split()[0] if company_clean else ""
                if company_first_word and company_first_word in line_words:
                    return company

                score = Levenshtein.ratio(company_first_word, line_words[0]) if line_words else 0
                if score > best_score and score > 0.6:
                    best_match = company
                    best_score = score

        return best_match

    def parse_metadata(self, text_blocks, filename):
        result = {
            "source": filename,
            "company": None,
            "model": None,
            "voltage": None,
            "capacity": None,
            "type": None
        }

        try:
            result["company"] = self.find_company_name(text_blocks)
        except:
            pass

        # model detection
        try:
            exclude_prefixes = ("iso", "iec", "din", "en", "ul")
            exclude_exact = {
                "20-hr", "hr", "mAh", "Ah", "V", "kV", "kHz", "MHz",
                "Hz", "mV", "W", "Wh", "kWh", "A", "mA", "ohm", "Ω",
                "°C", "°F", "rpm", "mm", "cm", "inch", "temp", "typ"
            }

            for line in text_blocks:
                tokens = re.findall(r'\b[\w\-\/]+\b', line)
                for token in tokens:
                    token_lower = token.lower()
                    if token_lower in exclude_exact or token_lower.startswith(exclude_prefixes):
                        continue
                    if len(token) >= 7 and re.search('[A-Za-z]', token) and re.search('[0-9]', token):
                        result["model"] = token
                        break
                if result["model"]:
                    break
        except:
            pass

        # Type detection 
        for line in text_blocks:
            for key, val in self.battery_type_map.items():
                if key.lower() in line.lower():
                    result["type"] = val
                    break
            if result["type"]:
                break

        # Voltage and capacity 
        for param, terms in self.keywords.items():
            for line in text_blocks:
                if any(term.lower() in line.lower() for term in terms):
                    value = self.extract_value(line, param)
                    if value:
                        result[param] = value
                        break

        if not result["voltage"]:
            for line in text_blocks:
                value = self.extract_value(line, "voltage")
                if value:
                    result["voltage"] = value
                    break

        if not result["capacity"]:
            for line in text_blocks:
                value = self.extract_value(line, "capacity")
                if value:
                    result["capacity"] = value
                    break

        return result

    def extract_value(self, text, param=None):
        patterns = {
            "voltage": r'(\d+\.?\d*)\s?V\b',
            "capacity": r'(\d+\.?\d*)\s?(mAh|Ah)\b',
        }

        if param and param in patterns:
            match = re.search(patterns[param], text, re.IGNORECASE)
            if match:
                return match.group().strip()
        return None


def process_csv(csv_path):
    parser = BatteryDatasheetParser()
    parser.load_company_list("battery_companies_list.txt")
    results = []

    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip():
                continue

            original_url = row[0].strip()
            if original_url.startswith(('http://', 'https://')):
                pdf_url = original_url
            elif original_url.startswith('//'):
                pdf_url = f'https:{original_url}'
            else:
                pdf_url = f'https://{original_url}'

            temp_file = None

            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    response = requests.get(pdf_url, stream=True, timeout=15)
                    response.raise_for_status()

                    content_type = response.headers.get('Content-Type', '')
                    if 'pdf' not in content_type.lower():
                        print(f"Skipping non-PDF content: {content_type}")
                        continue

                    for chunk in response.iter_content(8192):
                        tmp_file.write(chunk)
                    temp_file = tmp_file.name

                result = parser.process_datasheet(temp_file)
                results.append(result)

            except Exception as e:
                print(f"Failed to process {pdf_url}: {str(e)}")
            finally:
                if temp_file and os.path.exists(temp_file):
                    os.unlink(temp_file)

    return results


def kill_process():
    print("Timeout reached. Terminating process.")
    os._exit(1)  


if __name__ == "__main__":
    # Set timeout to 180 seconds (3 minutes)
    # timer = threading.Timer(180, kill_process)
    # timer.start()

    # try:
    results = process_csv("batteries_datasheets.csv")

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Successfully processed {len([r for r in results if not r.get('error')])} datasheets")

    with open("output_structured.csv", "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["company", "model", "voltage", "capacity", "type"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            metadata = r.get("metadata", {})
            if not metadata:
                continue
            writer.writerow({
                "company": metadata.get("company", ""),
                "model": metadata.get("model", ""),
                "voltage": metadata.get("voltage", ""),
                "capacity": metadata.get("capacity", ""),
                "type": metadata.get("type", "")
            })

    print(" CSV file 'output_structured.csv' written successfully.")
    # finally:
    #     timer.cancel()  # Cancel timeout if process completes
