import pandas as pd
import fitz  
import streamlit as st
import json
import os
from io import BytesIO
import cv2
import numpy as np
import pytesseract
from PIL import Image
from pathlib import Path
import urllib.parse
from playwright.sync_api import sync_playwright



def save_as_pdf(page, file_name):
    try:
        page.pdf(path=file_name, format="A4", print_background=True)
        print(f"Saved PDF using Playwright: {file_name}")
    except Exception as e:
        print(f"Failed to save PDF using Playwright: {e}")

def microsoft_print_to_pdf(page, file_name):
    try:
        page.keyboard.press("Control+P")  
        print("Triggered print dialog for Microsoft Print to PDF")
        page.wait_for_timeout(2000)
        page.keyboard.press("Enter")  
        print(f"Simulated saving to Microsoft Print to PDF: {file_name}")
    except Exception as e:
        print(f"Failed to simulate Microsoft Print to PDF: {e}")

def process_link(link, output_dir, category, result_data):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  
        page = browser.new_page()

        
        page.goto(link, wait_until="networkidle", timeout=60000)  
        parsed_url = urllib.parse.urlparse(link)
        filename = parsed_url.netloc.replace("www.", "") + parsed_url.path.replace("/", "_") + ".pdf"
        
        file_name_save_as_pdf = os.path.join(f"{filename}_save_as_pdf.pdf")
        file_name_microsoft_print_to_pdf = os.path.join(f"{filename}_microsoft_print_to_pdf.pdf")

        # Save as PDF using Playwright
        save_as_pdf(page, file_name_save_as_pdf)

        # Simulate Microsoft Print to PDF
        microsoft_print_to_pdf(page, file_name_microsoft_print_to_pdf)

        if category not in result_data:
            result_data[category] = [] 

        result_data[category].append({
            "url": link,
            "saveAsPdf": file_name_save_as_pdf,
            "printToPdf": file_name_microsoft_print_to_pdf
        })

        browser.close()

def load_links_from_json(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("JSON must be an object with categories as keys, each having a list of URLs.")
        return data


def detect_fonts_with_ocr(pdf_file):
    # Open the PDF
    doc = fitz.open(pdf_file)
    
    # Initialize analysis containers
    font_analysis = {
        'total_pages': len(doc),
        'small_fonts': 0,
        'large_fonts': 0,
        'total_text_elements': 0,
        'pages_font_details': []
    }
    
    # Process each page
    for page_num in range(len(doc)):
        # Get page
        page = doc[page_num]
        
        # Convert page to image
        pix = page.get_pixmap()
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        
        # Preprocess image
        opencv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(opencv_image, cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        # Perform OCR with detailed configuration
        details = pytesseract.image_to_data(
            thresh, 
            output_type=pytesseract.Output.DICT,
            config='--psm 6 -c preserve_interword_spaces=1'
        )
        
        # Page-specific font details
        page_font_details = {
            'page_number': page_num + 1,
            'small_fonts': 0,
            'large_fonts': 0,
            'total_text_elements': 0
        }
        
        # Analyze font sizes from OCR results
        for font_size in details['height']:
            # Filter out noise and very small values
            if 5 < font_size < 100:
                page_font_details['total_text_elements'] += 1
                font_analysis['total_text_elements'] += 1
                
                # Categorize font sizes
                if font_size < 10:
                    page_font_details['small_fonts'] += 1
                    font_analysis['small_fonts'] += 1
                else:
                    page_font_details['large_fonts'] += 1
                    font_analysis['large_fonts'] += 1
        
        font_analysis['pages_font_details'].append(page_font_details)
    
    # Calculate percentages
    total_text_elements = font_analysis['total_text_elements']
    font_analysis['small_fonts_percentage'] = (font_analysis['small_fonts'] / total_text_elements * 100) if total_text_elements else 0
    font_analysis['large_fonts_percentage'] = (font_analysis['large_fonts'] / total_text_elements * 100) if total_text_elements else 0
    
    return font_analysis

# Function to calculate margins
def calculate_page_margins(page):
    # Get all text blocks from the page
    text_instances = page.get_text("dict")["blocks"]
    images = page.get_images(full=True)

    if not text_instances and not images:
        return {"top": 0, "bottom": 0, "left": 0, "right": 0}

    # Initialize margin variables to extremes
    top_margin = page.rect.height
    bottom_margin = 0
    left_margin = page.rect.width
    right_margin = 0

    # Process each text block to find the margins
    for block in text_instances:
        if block["type"] == 0:  # Type 0 indicates text
            for line in block["lines"]:
                for span in line["spans"]:
                    # Adjust margins based on text position
                    if span["bbox"][1] < top_margin:
                        top_margin = span["bbox"][1]
                    if span["bbox"][3] > bottom_margin:
                        bottom_margin = span["bbox"][3]
                    if span["bbox"][0] < left_margin:
                        left_margin = span["bbox"][0]
                    if span["bbox"][2] > right_margin:
                        right_margin = span["bbox"][2]

    # If no text is found, set default margins
    if top_margin == page.rect.height:
        top_margin = 0
    if bottom_margin == 0:
        bottom_margin = page.rect.height
    if left_margin == page.rect.width:
        left_margin = 0
    if right_margin == 0:
        right_margin = page.rect.width

    # Convert to inches (72 points per inch)
    top_margin = round(top_margin / 72, 2)
    bottom_margin = round(bottom_margin / 72, 2)
    left_margin = round(left_margin / 72, 2)
    right_margin = round(right_margin / 72, 2)

    return {
        "top": top_margin,
        "bottom": bottom_margin,
        "left": left_margin,
        "right": right_margin,
        "image_count": len(images)
    }

# Function to extract text from PDF
@st.cache_data(show_spinner=False)
def extract_pdf_text(pdf_file):
    doc = fitz.open(pdf_file)
    all_text = []
    for page_number, page in enumerate(doc):
        text = page.get_text("text")
        if not text:
            text = ocr_pdf_page(page)
        all_text.append({
            "page_number": page_number + 1,
            "content": text
        })
    return all_text

# Function to extract text using OCR
def ocr_pdf_page(page):
    img = page.get_pixmap()
    pil_image = Image.frombytes("RGB", (img.width, img.height), img.samples)
    text = pytesseract.image_to_string(pil_image)
    return text

# Function to parse PDF to JSON
@st.cache_data(show_spinner=False)
def parse_pdf_to_json(pdf_file):
    if isinstance(pdf_file, list):
        pdf_file = pdf_file[0] 
    
    doc = fitz.open(pdf_file)
    result = []
    
    for page_number, page in enumerate(doc):
        text = page.get_text("text")
        page_data = {
            "page_number": page_number + 1,
            "text": text.strip()
        }
        result.append(page_data)
        
    return json.dumps(result, indent=4)

# Function to calculate text and image percentages
def calculate_text_and_image_percentage_from_json(json_data, pdf_file):
    page_data_list = []
    font_analysis = detect_fonts_with_ocr(pdf_file)

    for idx, page_data in enumerate(json_data.get('pages', [])):
        page_number = page_data.get('page_number')
        content = page_data.get('text', "")
        
        page_margins = calculate_page_margins(fitz.open(pdf_file)[page_number - 1])
        image_count = page_margins.get("image_count", 0)

        text_length = len(content)
        total_content = text_length + image_count * 1000
        text_percentage = (text_length / total_content) * 100 if total_content else 0
        image_percentage = (image_count * 1000 / total_content) * 100 if total_content else 0

        page_font_details = font_analysis['pages_font_details'][idx] if idx < len(font_analysis['pages_font_details']) else {}
        total_text_elements = page_font_details.get('total_text_elements', 1) or 1

        page_data_list.append({
            "page_number": page_number,
            "text_percentage": f"{text_percentage:.2f}%",  
            "image_percentage": f"{image_percentage:.2f}%",  
            "small_fonts_percentage": f"{(page_font_details.get('small_fonts', 0) / total_text_elements * 100):.2f}%",  
            "large_fonts_percentage": f"{(page_font_details.get('large_fonts', 0) / total_text_elements * 100):.2f}%",  
            "margins": {
                "top": page_margins["top"],
                "bottom": page_margins["bottom"],
                "left": page_margins["left"],
                "right": page_margins["right"],
            }
        })

    return page_data_list





def main():
    json_file_path = "cat.json"  
    output_dir = "output_pdfs"  
    os.makedirs(output_dir, exist_ok=True)

    
    data = load_links_from_json(json_file_path)

    result_data = {}

    for category, links in data.items():
        print(f"Processing category: {category}")
        for link in links:
            process_link(link, output_dir, category, result_data)

    #saving json
    result_json_path = "output_results.json"
    with open(result_json_path, 'w') as f:
        json.dump(result_data, f, indent=4)

    print(f"Results have been saved to: {result_json_path}")

    st.title("PDF Metadata Analyzer")

    st.write("Processing PDFs from the 'outputpdf' directory...")
    
    # Get list of PDF files from outputpdf directory
    pdf_files = list(output_dir.glob("*.pdf"))
    
    if not pdf_files:
        st.error("No PDF files found in the outputpdf directory.")
        return
        
    st.write(f"Found {len(pdf_files)} PDF files.")
    
    # List to accumulate metadata for all PDFs
    all_pdf_recipes = []

    # Button to process PDFs
    if st.button("Analyze PDFs"):
        json_outputs = {}

        for pdf_file in pdf_files:
            st.write(f"Processing {pdf_file.name}...")
            
            # Extract text and perform analysis
            all_text = extract_pdf_text(str(pdf_file))
            font_analysis = detect_fonts_with_ocr(str(pdf_file))
            json_str_output = parse_pdf_to_json(str(pdf_file))
            
            json_dict_output = {
                'pages': json.loads(json_str_output),
                'pages_info': []
            }

            page_data_list = calculate_text_and_image_percentage_from_json(json_dict_output, str(pdf_file))
            json_dict_output['pages_info'] = page_data_list
            
            json_outputs[str(pdf_file)] = json_dict_output

            # Add the metadata recipe for this PDF to the list
            pdf_metadata_recipe = {
                "saveAsPdf": Path(pdf_file).name,
                "metaDataSaveAsPdf": f"{Path(pdf_file).stem}_metadata.json",
                "metaDataPrintToPdf": f"{Path(pdf_file).stem}_metadata.json"
            }
            all_pdf_recipes.append(pdf_metadata_recipe)

            # Save JSON output for page data
            json_file = output_dir / f"{Path(pdf_file).stem}_metadata.json"
            with open(json_file, "w") as json_out:
                json.dump(json_dict_output, json_out, indent=4)
            

        # Generate final metadata recipe JSON file after processing all PDFs
        final_metadata_recipe = {
            "recipe": all_pdf_recipes
        }

        final_metadata_recipe_filename = output_dir / "all_pdfs_metadata_recipe.json"
        with open(final_metadata_recipe_filename, "w") as final_recipe_file:
            json.dump(final_metadata_recipe, final_recipe_file, indent=4)

        # Optionally, display the final recipe in the app
        st.json(final_metadata_recipe)

        st.success(f"All PDF metadata recipes saved to {final_metadata_recipe_filename}")
if __name__ == "__main__":
    main()
