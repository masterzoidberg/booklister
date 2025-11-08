"""
Quick syntax check for OCR implementation.
"""

# Test 1: OCR service import
try:
    from services.ocr import capabilities
    print("✓ OCR service imports successfully")
    print(f"Capabilities: {capabilities()}")
except Exception as e:
    print(f"✗ OCR service import failed: {e}")

# Test 2: OCR probe route import  
try:
    from routes import ocr_probe
    print("✓ OCR probe route imports successfully")
except Exception as e:
    print(f"✗ OCR probe route import failed: {e}")

# Test 3: Main import check
try:
    # Just check syntax without full import
    import ast
    with open('main.py', 'r') as f:
        ast.parse(f.read())
    print("✓ main.py syntax is valid")
except Exception as e:
    print(f"✗ main.py syntax error: {e}")

print("\nOCR implementation completed!")
