# Character Preservation Optimization

This document outlines the changes made to ensure the Gemini AI model preserves characters exactly as they appear in documents without any autocorrection or modifications.

## Changes Made

### 1. OCR Pipeline Prompt (`parser/ocr_pipeline.py`)

**Updated**: `structure_with_gemini_vision()` function prompt

**Key Changes**:
- Added explicit "NEVER" rules for autocorrection
- Emphasized EXACT character preservation
- Removed instructions to fix OCR errors or normalize data
- Added instructions to preserve original formatting, spacing, and case
- Changed goal from "clean, analysis-ready" to "EXACTLY as it appears"

**New Rules Added**:
- NEVER autocorrect, fix, or modify any characters
- NEVER fix OCR errors or typos - preserve exactly
- NEVER transliterate Amharic/Ethiopic characters
- NEVER normalize formatting or standardize dates/numbers
- NEVER change case or add missing punctuation

### 2. Services Prompts (`parser/services.py`)

**Updated**: Both `_build_parsing_prompt()` and `_build_vision_prompt()` methods

**Key Changes**:
- Replaced correction-focused instructions with preservation-focused ones
- Added comprehensive "NEVER" rules for character modifications
- Emphasized copying each character, symbol, and space exactly
- Removed normalization and standardization instructions

### 3. Generation Configuration (`parser/ocr_pipeline.py`)

**Updated**: `_get_gen_config()` function

**Changes**:
- Temperature: `0.15` → `0.0` (maximum determinism)
- Top_p: `0.9` → `0.1` (more focused predictions)
- Top_k: `40` → `1` (most deterministic setting)
- Max tokens: `4000` → `8000` (handle larger documents)

### 4. Environment Configuration (`.env.example`)

**Updated**: Default values for character preservation

**Changes**:
- `GEMINI_TEMPERATURE`: `0.1` → `0.0`
- `GEMINI_MAX_OUTPUT_TOKENS`: `1500` → `8000`
- `GEMINI_MODEL`: Recommended `gemini-2.5-flash` for better accuracy
- Added documentation about character preservation focus

## Impact

These changes ensure that:

1. **No Autocorrection**: The AI will not "fix" perceived errors or typos
2. **Exact Transcription**: Every character, space, and symbol is preserved
3. **Original Formatting**: Dates, numbers, and text formatting remain unchanged
4. **Script Preservation**: Amharic/Ethiopic characters are not transliterated
5. **Case Sensitivity**: Original uppercase/lowercase is maintained
6. **Deterministic Output**: Lower temperature ensures consistent results

## Usage Notes

- The system now prioritizes accuracy over "cleanliness"
- Users will see documents transcribed exactly as written, including any errors
- Processing may take slightly longer due to increased token limits
- Results will be more faithful to the original document content

## Testing Recommendations

Test with documents containing:
- Mixed languages (English + Amharic)
- Handwritten text
- Unclear or damaged text
- Non-standard formatting
- Intentional abbreviations or shorthand

Verify that all text appears exactly as written without corrections or modifications.
