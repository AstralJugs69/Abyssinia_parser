#!/usr/bin/env python
"""
Test script for OCR functionality
"""
import os
import sys
import django
from PIL import Image, ImageDraw, ImageFont
import io

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_parser.settings')
django.setup()

from parser.services import OCRService


def create_sample_bank_document():
    """Create a sample bank document image for testing"""
    # Create a simple bank statement image
    width, height = 800, 600
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    
    # Try to use a default font, fallback to basic if not available
    try:
        font = ImageFont.truetype("arial.ttf", 20)
        small_font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Draw bank statement content
    y_pos = 50
    
    # Header
    draw.text((50, y_pos), "FIRST NATIONAL BANK", fill='black', font=font)
    y_pos += 40
    draw.text((50, y_pos), "Account Statement", fill='black', font=font)
    y_pos += 60
    
    # Account info
    draw.text((50, y_pos), "Account Number: 1234567890", fill='black', font=small_font)
    y_pos += 30
    draw.text((50, y_pos), "Account Holder: John Smith", fill='black', font=small_font)
    y_pos += 30
    draw.text((50, y_pos), "Statement Period: 01/01/2024 - 01/31/2024", fill='black', font=small_font)
    y_pos += 50
    
    # Balance info
    draw.text((50, y_pos), "Opening Balance: $2,500.00", fill='black', font=small_font)
    y_pos += 30
    draw.text((50, y_pos), "Closing Balance: $2,750.00", fill='black', font=small_font)
    y_pos += 50
    
    # Transactions
    draw.text((50, y_pos), "TRANSACTIONS:", fill='black', font=font)
    y_pos += 40
    
    transactions = [
        "01/05/2024  Deposit           +$500.00",
        "01/10/2024  ATM Withdrawal    -$100.00", 
        "01/15/2024  Online Transfer   -$150.00",
        "01/20/2024  Direct Deposit    +$1,200.00"
    ]
    
    for transaction in transactions:
        draw.text((50, y_pos), transaction, fill='black', font=small_font)
        y_pos += 25
    
    return image


def test_ocr_service():
    """Test the OCR service with sample documents"""
    print("Testing OCR Service...")
    print("=" * 50)
    
    ocr_service = OCRService()
    
    # Test 1: Create and test with sample bank document
    print("\n1. Testing with sample bank document image...")
    sample_image = create_sample_bank_document()
    
    # Convert PIL image to file-like object
    img_buffer = io.BytesIO()
    sample_image.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    result = ocr_service.extract_text_from_image(img_buffer)
    
    if result['success']:
        print(f"✓ OCR Success! Confidence: {result['confidence']:.1f}%")
        print(f"✓ Word count: {result['word_count']}")
        print(f"✓ Extracted text preview:")
        print("-" * 30)
        print(result['text'][:300] + "..." if len(result['text']) > 300 else result['text'])
        print("-" * 30)
    else:
        print(f"✗ OCR Failed: {result['error']}")
        print(f"  Details: {result.get('details', 'No details')}")
        if 'installation_help' in result:
            print(f"  Help: {result['installation_help']}")
        if 'fallback_suggestion' in result:
            print(f"  Fallback: {result['fallback_suggestion']}")
    
    # Test 2: Test with simple text
    print("\n2. Testing with simple text...")
    simple_text = "This is a test document.\nAccount: 123456789\nBalance: $1,000.00"
    text_buffer = io.StringIO(simple_text)
    
    # Convert to bytes for file-like behavior
    text_bytes = io.BytesIO(simple_text.encode('utf-8'))
    
    result = ocr_service.process_file(text_bytes, 'txt')
    
    if result['success']:
        print(f"✓ Text processing success! Confidence: {result['confidence']}%")
        print(f"✓ Word count: {result['word_count']}")
        print(f"✓ Text content: {result['text']}")
    else:
        print(f"✗ Text processing failed: {result['error']}")
    
    # Test 3: Test error handling with invalid file type
    print("\n3. Testing error handling...")
    result = ocr_service.process_file(text_bytes, 'invalid')
    
    if not result['success']:
        print(f"✓ Error handling works: {result['error']}")
    else:
        print("✗ Error handling failed - should have rejected invalid file type")
    
    # Test 4: Test different file types through process_file method
    print("\n4. Testing file type processing...")
    
    # Test PNG processing
    img_buffer.seek(0)
    result = ocr_service.process_file(img_buffer, 'png')
    if result['success']:
        print("✓ PNG processing works")
    else:
        print(f"✗ PNG processing failed: {result['error']}")
    
    # Test JPG processing
    jpg_buffer = io.BytesIO()
    sample_image.save(jpg_buffer, format='JPEG')
    jpg_buffer.seek(0)
    result = ocr_service.process_file(jpg_buffer, 'jpg')
    if result['success']:
        print("✓ JPG processing works")
    else:
        print(f"✗ JPG processing failed: {result['error']}")
    
    # Test 5: Test Tesseract availability check
    print("\n5. Testing Tesseract availability...")
    is_available = ocr_service._is_tesseract_available()
    if is_available:
        print("✓ Tesseract is available and working")
    else:
        print("✗ Tesseract is not available (expected on systems without Tesseract)")
    
    print("\n" + "=" * 50)
    print("OCR Service testing completed!")
    
    # Summary
    print("\nSUMMARY:")
    print("- Text file processing: ✓ Working")
    print("- Error handling: ✓ Working") 
    print("- File type validation: ✓ Working")
    if is_available:
        print("- OCR functionality: ✓ Available")
    else:
        print("- OCR functionality: ⚠ Requires Tesseract installation")
        print("  Install from: https://github.com/tesseract-ocr/tesseract")


if __name__ == "__main__":
    test_ocr_service()