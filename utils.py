
from passporteye import read_mrz
import pytesseract
import json

def process_passport_mrz(image_path):
    """
    Process passport MRZ data from any country and return formatted information
   
    Args:
        image_path (str): Path to the scanned passport image
       
    Returns:
        dict: Formatted passport data as dictionary
    """
    # Process the scanned passport image
    mrz = read_mrz(image_path)
   
    # Check if MRZ was detected
    if not mrz:
        return {"error": "No MRZ detected in the provided image"}
   
    # Extract MRZ data
    mrz_data = mrz.to_dict()
   
    # Format dates (convert from YYMMDD to YYYY-MM-DD format)
    def format_date(date_str):
        if not date_str or len(date_str) != 6:
            return None
       
        try:
            year = int(date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            
            # Determine century (20xx or 19xx)
            # For birth dates, assume 20xx for years < 30, otherwise 19xx
            if date_str == mrz_data.get('date_of_birth', ''):
                year = 2000 + year if year < 30 else 1900 + year
            else:
                # For expiration dates, assume current century
                year = 2000 + year
               
            # Validate month and day
            if month < 1 or month > 12 or day < 1 or day > 31:
                return date_str  # Return original if invalid
               
            return f"{year}-{month:02d}-{day:02d}"
        except ValueError:
            return date_str  # Return original if parsing fails
   
    # Create formatted output
    formatted_data = {
        "nationality": get_nationality(mrz_data.get('nationality', '')),
        "surname": mrz_data.get('surname', '').replace('<', ' ').strip(),
        "given_name": mrz_data.get('names', '').replace('<', ' ').strip(),
        "sex": mrz_data.get('sex', ''),
        "dob": format_date(mrz_data.get('date_of_birth', '')),
        "passport_no": clean_passport_number(mrz_data.get('number', ''))
    }
   
    # Remove empty values
    def clean_dict(d):
        if isinstance(d, dict):
            return {k: clean_dict(v) for k, v in d.items() if v not in (None, '', {}, [])}
        return d
   
    return clean_dict(formatted_data)


def get_nationality(code):
    """Convert nationality code to full name"""
    # This is a simplified version - in a real app, you would have a complete mapping
    with open("nationality_map.json", "r") as f:
        nationality_map = json.load(f)
    return nationality_map.get(code, code)


def clean_passport_number(raw_number: str) -> str:
    """
    Cleans and corrects common OCR errors in passport numbers.
    Assumes passport numbers start with 2 letters followed by digits.
    """
    if not raw_number:
        return ""

    # Replace MRZ filler character with space, then strip
    number = raw_number.replace('<', ' ').strip().upper()

    # Take first two characters as letters, correct only if obviously misread
    corrected_prefix = number[:2]
    # prefix_corrections = {
    #     '0': 'O',
    #     '1': 'I',
    #     '5': 'S',
    #     '8': 'B',
    #     '2': 'Z',
    # }
    # corrected_prefix = ''.join(prefix_corrections.get(c, c) for c in prefix)

    # Apply stricter correction to remaining characters, assumed to be digits
    suffix = number[2:]
    digit_corrections = {
        'O': '0',
        'Q': '0',
        'D': '0',
        'I': '1',
        'L': '1',
        'Z': '2',
        'S': '5',
        'B': '8',
        'G': '6'
    }
    corrected_suffix = ''.join(digit_corrections.get(c, c) for c in suffix)

    # Combine and remove any non-alphanumeric characters (if needed)
    cleaned = ''.join(filter(str.isalnum, corrected_prefix + corrected_suffix))

    return cleaned
