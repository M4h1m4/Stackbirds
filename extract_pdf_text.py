#!/usr/bin/env python3
"""
Simple script to extract text from PDF files.
Run: python3 extract_pdf_text.py
"""

import sys
import os

def extract_with_pypdf2():
    """Try to extract text using PyPDF2"""
    try:
        import PyPDF2
        pdf_path = "Stackbirds Full Stack Spring Internship 2026.pdf"
        
        if not os.path.exists(pdf_path):
            print(f"Error: {pdf_path} not found")
            return False
            
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page_num, page in enumerate(pdf_reader.pages):
                text += f"\n--- Page {page_num + 1} ---\n"
                text += page.extract_text()
            
            output_file = "assessment_text.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
            print(f"✓ Text extracted successfully to {output_file}")
            print(f"Total pages: {len(pdf_reader.pages)}")
            return True
    except ImportError:
        print("PyPDF2 not installed. Install with: pip3 install PyPDF2")
        return False
    except Exception as e:
        print(f"Error extracting text: {e}")
        return False

def extract_with_pdfplumber():
    """Try to extract text using pdfplumber (better for tables)"""
    try:
        import pdfplumber
        pdf_path = "Stackbirds Full Stack Spring Internship 2026.pdf"
        
        if not os.path.exists(pdf_path):
            print(f"Error: {pdf_path} not found")
            return False
            
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text += f"\n--- Page {page_num + 1} ---\n"
                text += page.extract_text()
        
        output_file = "assessment_text.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(text)
        
        print(f"✓ Text extracted successfully to {output_file}")
        print(f"Total pages: {len(pdf.pages)}")
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"Error extracting text: {e}")
        return False

if __name__ == "__main__":
    print("Attempting to extract text from PDF...")
    
    # Try pdfplumber first (better quality)
    if extract_with_pdfplumber():
        sys.exit(0)
    
    # Fall back to PyPDF2
    if extract_with_pypdf2():
        sys.exit(0)
    
    print("\nNo PDF libraries found. Please install one:")
    print("  pip3 install PyPDF2")
    print("  or")
    print("  pip3 install pdfplumber")
    sys.exit(1)
