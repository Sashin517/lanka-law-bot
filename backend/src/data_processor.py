import os
import shutil
import json
import re
import subprocess

# Define local paths relative to this script's location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# We will keep the raw repo here permanently so we don't have to re-download it
TEMP_REPO_DIR = os.path.join(BASE_DIR, "temp_lk_legal_docs") 
# The clean, filtered JSONs go here
DATA_DIR = os.path.join(BASE_DIR, "data")

def fetch_and_filter_acts():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Check if we already downloaded the raw data
    if not os.path.exists(TEMP_REPO_DIR):
        print("Downloading raw data from GitHub... (This only happens once)")
        subprocess.run(["git", "clone", "-b", "data_lk_acts", "--single-branch", "https://github.com/nuuuwan/lk_legal_docs.git", TEMP_REPO_DIR])
    else:
        print("Raw data already found locally! Skipping download.")

    # Filter logic
    print("\nFiltering for Contract & Litigation Acts...")
    target_keywords = [
        "contract", "rent", "lease", "tenancy", "civil procedure",
        "evidence", "arbitration", "sale of goods", "company", "companies",
        "consumer", "property", "land", "mortgage", "trust",
        "employment", "labour", "commercial", "debt", "recovery", "eviction"
    ]
    pattern = re.compile(r'\b(' + '|'.join(target_keywords) + r')\b', re.IGNORECASE)
    
    source_dir = os.path.join(TEMP_REPO_DIR, "data", "lk_acts")
    copied_count = 0
    scanned_count = 0

    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".json"):
                file_path = os.path.join(root, file)
                scanned_count += 1
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            continue
                        
                        text_to_search = ""
                        if isinstance(data, list):
                            for block in data[:30]:
                                if 'text' in block:
                                    text_to_search += block['text'].lower() + " "

                        if pattern.search(text_to_search):
                            # --- BETTER NAMING CONVENTION ---
                            # Extract the year and act number from the folder paths
                            act_number = os.path.basename(root)
                            act_year = os.path.basename(os.path.dirname(root))
                            
                            new_filename = f"Year_{act_year}_Act_{act_number}.json"
                            dest_path = os.path.join(DATA_DIR, new_filename)
                            
                            # Save the file with the new, meaningful name
                            shutil.copy2(file_path, dest_path)
                            copied_count += 1
                except Exception:
                    continue

    print(f"\nSUCCESS! Scanned {scanned_count} JSON files.")
    print(f"Extracted and saved {copied_count} highly relevant Acts to {DATA_DIR}")
    
    # Notice we DO NOT delete TEMP_REPO_DIR anymore at the end!
    # This allows us to run the script again instantly.

if __name__ == "__main__":
    fetch_and_filter_acts()