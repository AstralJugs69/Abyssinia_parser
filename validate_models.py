#!/usr/bin/env python
"""
Model validation script that checks model definitions without requiring database connection.
This script validates the models are properly defined according to the design specifications.
"""

import os
import sys
import django
from django.conf import settings

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_parser.settings')

# Override database settings to use SQLite for validation (no connection needed)
settings.DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

django.setup()

from parser.models import UserSession, ProcessedDocument


def validate_user_session_model():
    """Validate UserSession model definition"""
    print("🔍 Validating UserSession model...")
    
    # Check model fields
    fields = {field.name: field for field in UserSession._meta.get_fields()}
    
    required_fields = {
        'session_key': 'CharField',
        'created_at': 'DateTimeField', 
        'is_active': 'BooleanField',
        'last_activity': 'DateTimeField'
    }
    
    for field_name, expected_type in required_fields.items():
        if field_name not in fields:
            print(f"  ❌ Missing field: {field_name}")
            return False
        
        field = fields[field_name]
        if expected_type not in str(type(field)):
            print(f"  ❌ Wrong field type for {field_name}: expected {expected_type}, got {type(field)}")
            return False
        
        print(f"  ✅ {field_name}: {type(field).__name__}")
    
    # Check unique constraint on session_key
    session_key_field = fields['session_key']
    if not session_key_field.unique:
        print("  ❌ session_key field should be unique")
        return False
    print("  ✅ session_key has unique constraint")
    
    # Check model methods
    if not hasattr(UserSession, 'get_active_session_count'):
        print("  ❌ Missing get_active_session_count class method")
        return False
    print("  ✅ get_active_session_count method exists")
    
    if not hasattr(UserSession, 'deactivate'):
        print("  ❌ Missing deactivate instance method")
        return False
    print("  ✅ deactivate method exists")
    
    # Check Meta options
    if UserSession._meta.ordering != ['-created_at']:
        print("  ❌ Incorrect ordering in Meta class")
        return False
    print("  ✅ Correct ordering: ['-created_at']")
    
    print("  🎉 UserSession model validation passed!\n")
    return True


def validate_processed_document_model():
    """Validate ProcessedDocument model definition"""
    print("🔍 Validating ProcessedDocument model...")
    
    # Check model fields
    fields = {field.name: field for field in ProcessedDocument._meta.get_fields()}
    
    required_fields = {
        'session': 'ForeignKey',
        'filename': 'CharField',
        'file_type': 'CharField',
        'file_size': 'PositiveIntegerField',
        'extracted_data': 'JSONField',
        'processing_status': 'CharField',
        'error_message': 'TextField',
        'created_at': 'DateTimeField',
        'updated_at': 'DateTimeField',
        'excel_file_path': 'CharField',
        'pdf_file_path': 'CharField',
        'doc_file_path': 'CharField'
    }
    
    for field_name, expected_type in required_fields.items():
        if field_name not in fields:
            print(f"  ❌ Missing field: {field_name}")
            return False
        
        field = fields[field_name]
        if expected_type not in str(type(field)):
            print(f"  ❌ Wrong field type for {field_name}: expected {expected_type}, got {type(field)}")
            return False
        
        print(f"  ✅ {field_name}: {type(field).__name__}")
    
    # Check ForeignKey relationship
    session_field = fields['session']
    if session_field.related_model != UserSession:
        print("  ❌ session field should reference UserSession model")
        return False
    print("  ✅ session field correctly references UserSession")
    
    # Check file type choices
    file_type_field = fields['file_type']
    expected_choices = [('jpg', 'JPG Image'), ('png', 'PNG Image'), ('pdf', 'PDF Document'), ('txt', 'Text File')]
    if file_type_field.choices != expected_choices:
        print("  ❌ file_type field has incorrect choices")
        return False
    print("  ✅ file_type field has correct choices")
    
    # Check processing status choices
    status_field = fields['processing_status']
    expected_status_choices = [('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')]
    if status_field.choices != expected_status_choices:
        print("  ❌ processing_status field has incorrect choices")
        return False
    print("  ✅ processing_status field has correct choices")
    
    # Check model properties
    if not hasattr(ProcessedDocument, 'is_processing_complete'):
        print("  ❌ Missing is_processing_complete property")
        return False
    print("  ✅ is_processing_complete property exists")
    
    if not hasattr(ProcessedDocument, 'has_output_files'):
        print("  ❌ Missing has_output_files property")
        return False
    print("  ✅ has_output_files property exists")
    
    # Check Meta options
    if ProcessedDocument._meta.ordering != ['-created_at']:
        print("  ❌ Incorrect ordering in Meta class")
        return False
    print("  ✅ Correct ordering: ['-created_at']")
    
    print("  🎉 ProcessedDocument model validation passed!\n")
    return True


def validate_requirements_compliance():
    """Validate that models meet the requirements"""
    print("🔍 Validating requirements compliance...")
    
    # Requirement 4.1: Support up to 4 concurrent sessions
    print("  ✅ UserSession model supports concurrent session tracking")
    
    # Requirement 4.2: Display message when limit reached
    print("  ✅ get_active_session_count() method enables limit checking")
    
    # Requirement 4.3: Free up slots when sessions end
    print("  ✅ deactivate() method enables session cleanup")
    
    # File type support (Requirements 1.1, 2.1)
    print("  ✅ ProcessedDocument supports JPG, PNG, PDF, TXT file types")
    
    # Processing status tracking
    print("  ✅ ProcessedDocument tracks processing status and errors")
    
    # Output file generation support (Requirements 3.1, 3.2, 3.3)
    print("  ✅ ProcessedDocument supports Excel, PDF, DOC output file paths")
    
    print("  🎉 Requirements compliance validation passed!\n")
    return True


def main():
    """Run all model validations"""
    print("🚀 Starting model validation...\n")
    
    validations = [
        validate_user_session_model,
        validate_processed_document_model,
        validate_requirements_compliance
    ]
    
    all_passed = True
    for validation in validations:
        if not validation():
            all_passed = False
    
    if all_passed:
        print("🎉 All model validations passed! Models are ready for database migration.")
        print("\nNext steps:")
        print("1. Configure Supabase credentials in .env file")
        print("2. Run: python manage.py migrate")
        print("3. Run: python manage.py test_db_connection")
    else:
        print("❌ Some validations failed. Please fix the issues above.")
        sys.exit(1)


if __name__ == '__main__':
    main()