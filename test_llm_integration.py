#!/usr/bin/env python
"""
Test script for LLM integration with Gemini API
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).resolve().parent
sys.path.append(str(project_dir))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_parser.settings')
django.setup()

from parser.services import LLMService, DataStructuringService

def test_gemini_api():
    """Test Gemini API connection and parsing"""
    print("Testing Gemini API integration...")
    
    # Initialize LLM service
    llm_service = LLMService()
    
    # Test API connection
    print("\n1. Testing API connections...")
    api_status = llm_service.test_api_connection()
    
    for provider, status in api_status.items():
        if status['available']:
            print(f"✅ {provider.upper()} API: Connected")
        else:
            print(f"❌ {provider.upper()} API: {status['error']}")
    
    # Test document parsing with sample banking text
    print("\n2. Testing document parsing...")
    
    sample_banking_text = """
    BANK OF AMERICA
    Account Statement
    
    Account Holder: John Smith
    Account Number: 1234567890
    Statement Period: January 1, 2024 - January 31, 2024
    
    Current Balance: $2,450.75
    Available Balance: $2,200.75
    
    TRANSACTIONS:
    01/05/2024  Direct Deposit - Salary        +$3,200.00
    01/08/2024  ATM Withdrawal                 -$100.00
    01/12/2024  Online Purchase - Amazon       -$45.99
    01/15/2024  Monthly Fee                    -$12.00
    01/20/2024  Transfer to Savings            -$500.00
    01/25/2024  Gas Station Purchase           -$35.50
    
    Monthly Summary:
    Total Deposits: $3,200.00
    Total Withdrawals: $693.49
    Fees Charged: $12.00
    
    Bank Information:
    Bank Name: Bank of America
    Routing Number: 021000322
    Branch: Main Street Branch
    """
    
    # Parse the sample text
    parsing_result = llm_service.parse_banking_document(sample_banking_text, "bank_statement")
    
    if parsing_result['success']:
        print("✅ Document parsing: Success")
        print(f"   Provider: {parsing_result['provider']}")
        print(f"   Confidence: {parsing_result['confidence']:.2f}")
        
        # Test data structuring
        print("\n3. Testing data structuring...")
        structuring_service = DataStructuringService()
        structured_result = structuring_service.structure_banking_data(parsing_result['data'])
        
        if structured_result['success']:
            print("✅ Data structuring: Success")
            
            # Display some key results
            structured_data = structured_result['data']
            summary = structured_data['summary']
            
            print(f"\n📊 Extracted Summary:")
            print(f"   Account Holder: {summary.get('account_holder', 'N/A')}")
            print(f"   Account Number: {summary.get('account_number', 'N/A')}")
            print(f"   Current Balance: {summary.get('current_balance', 'N/A')}")
            print(f"   Transaction Count: {summary.get('transaction_count', 0)}")
            
            # Show data quality assessment
            quality = structured_data['metadata']['data_quality']
            print(f"\n📈 Data Quality:")
            print(f"   Completeness: {quality['completeness_score']:.2f}")
            print(f"   Filled Fields: {quality['filled_fields']}/{quality['total_fields']}")
            
            # Show some transactions
            transactions = structured_data['transactions'][:3]  # First 3 transactions
            if transactions:
                print(f"\n💳 Sample Transactions:")
                for tx in transactions:
                    print(f"   {tx['date']} | {tx['description']} | {tx['formatted_amount']}")
        else:
            print(f"❌ Data structuring failed: {structured_result['error']}")
    else:
        print(f"❌ Document parsing failed: {parsing_result['error']}")
        if 'details' in parsing_result:
            print(f"   Details: {parsing_result['details']}")

def main():
    """Main test function"""
    print("🚀 Document Parser LLM Integration Test")
    print("=" * 50)
    
    try:
        test_gemini_api()
        print("\n✅ All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()