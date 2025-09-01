from django import forms
from django.core.exceptions import ValidationError
import os


class DocumentUploadForm(forms.Form):
    """Form for uploading documents with validation"""
    
    ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf']
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes
    
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'file-input',
            'accept': '.jpg,.jpeg,.png,.pdf',
            'id': 'id_file'
        }),
        help_text='Supported formats: JPG, PNG, PDF (Max size: 10MB)'
    )

    OCR_ENGINE_CHOICES = (
        ('tesseract_gemini', 'Tesseract OCR + Gemini 2.0 Cleanup'),
        ('gemini_vision', 'Gemini 2.0 Vision (Direct Processing)'),
    )
    ocr_engine = forms.ChoiceField(
        choices=OCR_ENGINE_CHOICES,
        initial='tesseract_gemini',
        widget=forms.RadioSelect(attrs={'class': 'ocr-choice'}),
        help_text='Choose your OCR processing method.'
    )

    OUTPUT_CHOICES = (
        ('excel', 'Excel (.xlsx)'),
        ('pdf', 'PDF'),
    )
    output_format = forms.ChoiceField(
        choices=OUTPUT_CHOICES,
        initial='excel',
        widget=forms.RadioSelect(attrs={'class': 'output-choice'}),
        help_text='Choose your preferred output format.'
    )
    
    def clean_file(self):
        """Validate uploaded file"""
        file = self.cleaned_data.get('file')
        
        if not file:
            raise ValidationError("No file was uploaded.")
        
        # Check file size
        if file.size > self.MAX_FILE_SIZE:
            raise ValidationError(
                f"File size ({file.size / (1024*1024):.1f}MB) exceeds the maximum allowed size of 10MB."
            )
        
        # Check file extension
        file_extension = os.path.splitext(file.name)[1].lower()
        if file_extension not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"File type '{file_extension}' is not supported. "
                f"Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )
        
        # Additional validation for specific file types
        if file_extension in ['.jpg', '.jpeg', '.png']:
            # Basic image validation
            if not file.content_type.startswith('image/'):
                raise ValidationError("Invalid image file.")
        elif file_extension == '.pdf':
            if file.content_type != 'application/pdf':
                raise ValidationError("Invalid PDF file.")
        
        return file
    
    def get_file_type(self):
        """Get the file type based on extension"""
        if hasattr(self, 'cleaned_data') and 'file' in self.cleaned_data:
            file = self.cleaned_data['file']
            extension = os.path.splitext(file.name)[1].lower()
            
            if extension in ['.jpg', '.jpeg']:
                return 'jpg'
            elif extension == '.png':
                return 'png'
            elif extension == '.pdf':
                return 'pdf'
        
        return None