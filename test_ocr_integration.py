#!/usr/bin/env python
"""
Integration test for OCR functionality with Django views
"""
import os
import sys
import django
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
import json
import io
from PIL import Image, ImageDraw, ImageFont

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_parser.settings')
django.setup()

from parser.models import UserSession, ProcessedDocument
from parser.services import OCRService


def create_test_image():
    """Create a simple test image with text"""
    width, height = 400, 200
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    
    # Add some text
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()
    
    draw.text((20, 50), "Test Bank Document", fill='black', font=font)
    draw.text((20, 80), "Account: 123456789", fill='black', font=font)
    draw.text((20, 110), "Balance: $1,500.00", fill='black', font=font)
    
    return image


def test_ocr_integration():
    """Test OCR integration with Django views"""
    print("Testing OCR Integration with Django...")
    print("=" * 50)
    
    # Create test client
    client = Client()
    
    # Test 1: Test OCR service directly
    print("\n1. Testing OCR service directly...")
    ocr_service = OCRService()
    
    # Create test image
    test_image = create_test_image()
    img_buffer = io.BytesIO()
    test_image.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    result = ocr_service.process_file(img_buffer, 'png')
    
    if result['success']:
        print(f"✓ OCR service works: {result['confidence']:.1f}% confidence")
        print(f"✓ Extracted: {result['text'][:100]}...")
    else:
        print(f"✗ OCR service failed: {result['error']}")
        print(f"  This is expected if Tesseract is not installed")
    
    # Test 2: Test text file processing
    print("\n2. Testing text file processing...")
    test_text = "Bank Statement\nAccount: 987654321\nBalance: $2,000.00"
    text_buffer = io.BytesIO(test_text.encode('utf-8'))
    
    result = ocr_service.process_file(text_buffer, 'txt')
    
    if result['success']:
        print(f"✓ Text processing works: {result['confidence']}% confidence")
        print(f"✓ Content: {result['text']}")
    else:
        print(f"✗ Text processing failed: {result['error']}")
    
    # Test 3: Test file upload endpoint
    print("\n3. Testing file upload endpoint...")
    
    # Create a simple text file for upload
    test_file_content = b"Test document content\nAccount Number: 555666777\nAmount: $500.00"
    uploaded_file = SimpleUploadedFile(
        "test_document.txt",
        test_file_content,
        content_type="text/plain"
    )
    
    try:
        response = client.post('/upload-ajax/', {
            'file': uploaded_file
        })
        
        if response.status_code == 200:
            data = json.loads(response.content)
            if data.get('success'):
                print(f"✓ File upload successful: {data.get('filename')}")
                document_id = data.get('document_id')
                
                # Test 4: Test document processing endpoint
                print("\n4. Testing document processing endpoint...")
                
                process_response = client.post('/process-document/', 
                    json.dumps({'document_id': document_id}),
                    content_type='application/json'
                )
                
                if process_response.status_code == 200:
                    process_data = json.loads(process_response.content)
                    if process_data.get('success'):
                        print(f"✓ Document processing successful")
                        print(f"✓ Extracted text: {process_data['data']['text'][:100]}...")
                        print(f"✓ Confidence: {process_data['data']['confidence']}%")
                    else:
                        print(f"✗ Document processing failed: {process_data.get('error')}")
                else:
                    print(f"✗ Processing endpoint error: {process_response.status_code}")
            else:
                print(f"✗ Upload failed: {data.get('error')}")
        else:
            print(f"✗ Upload endpoint error: {response.status_code}")
            
    except Exception as e:
        print(f"✗ Integration test error: {str(e)}")
    
    print("\n" + "=" * 50)
    print("OCR Integration testing completed!")
    
    # Cleanup
    print("\n5. Cleaning up test data...")
    try:
        # Clean up any test documents
        ProcessedDocument.objects.filter(filename__contains='test').delete()
        print("✓ Test data cleaned up")
    except Exception as e:
        print(f"⚠ Cleanup warning: {str(e)}")


if __name__ == "__main__":
    test_ocr_integration()