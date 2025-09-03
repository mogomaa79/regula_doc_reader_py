import re
from fuzzywuzzy import fuzz
import pandas as pd

def get_string_value(field_value):
    """Extract string value from CertainField or regular value"""
    if field_value is None:
        return ""
    if hasattr(field_value, '__str__'):
        str_value = str(field_value)
        # Handle "nan", "NaN", "NAN" strings specifically
        if str_value.lower() in ['nan', 'none', 'null']:
            return ""
        return str_value
    return str(field_value) if field_value else ""

def get_certainty(field_value):
    """Extract certainty from CertainField or return False for regular values"""
    if hasattr(field_value, 'certainty'):
        return field_value.certainty
    return False

def update_field_with_certainty(formatted_data, field_name, new_value, certainty=None):
    """Update a field with proper certainty handling"""
    try:
        from src.passport_extraction import CertainField
        
        old_field = formatted_data.get(field_name, "")
        if certainty is None:
            certainty = get_certainty(old_field)
        
        # Handle None values
        if new_value is None:
            new_value = ""
        
        formatted_data[field_name] = CertainField(str(new_value), certainty)
    except ImportError:
        formatted_data[field_name] = str(new_value) if new_value is not None else ""

def correct_ocr_characters(text):
    if not text or not isinstance(text, str):
        return text
    
    # Common OCR character corrections
    corrections = {
        'O': '0',  # Letter O to digit 0
        'I': '1',  # Letter I to digit 1
        'S': '5',  # Letter S to digit 5
        'B': '8',  # Letter B to digit 8
        'G': '6',  # Letter G to digit 6
        'Z': '2',  # Letter Z to digit 2
        'D': '0',  # Letter D to digit 0
        'l': '1',  # Lowercase L to digit 1
        'o': '0',  # Lowercase O to digit 0
        's': '5',  # Lowercase S to digit 5
        'g': '6',  # Lowercase G to digit 6
        'z': '2',  # Lowercase Z to digit 2
    }
    
    # Apply corrections
    corrected_text = ""
    for char in text:
        corrected_text += corrections.get(char, char)
    
    return corrected_text

def correct_ocr_digit_section(text, start_pos, end_pos):
    if not text or start_pos >= len(text) or end_pos > len(text) or start_pos >= end_pos:
        return text
    
    # Extract the section to correct
    section = text[start_pos:end_pos]
    corrected_section = correct_ocr_characters(section)
    
    # Reconstruct the text with corrected section
    return text[:start_pos] + corrected_section + text[end_pos:]

def derive_country_of_issue(place_of_issue):
    """
    Smart function to derive country of issue from place of issue.
    Handles various mapping rules and patterns.
    """
    if not place_of_issue or not isinstance(place_of_issue, str):
        return ""
    
    place = place_of_issue.strip().upper()
    
    city_country_map = pd.read_csv("static/city_country.csv")
    city_country_map = dict(zip(city_country_map["city"], city_country_map["country"]))

    most_similar = 0
    for city in city_country_map.keys():
        ratio = fuzz.partial_ratio(place, city)
        if ratio > most_similar:
            most_similar = ratio
            city_of_issue = city
            country_of_issue = city_country_map[city]

    if most_similar >= 90:
        return country_of_issue, city_of_issue
    
    return "", ""

def philippines_rules(formatted_data):  
    def process_number(number_str):
        if not number_str or not isinstance(number_str, str):
            return "", False
        
        number = number_str.strip().upper()
        
        # Length check - must be exactly 9 characters
        if len(number) < 9: return number, False
        if len(number) > 9:
            return number[:9], False
        
        number = correct_ocr_digit_section(number, 1, 8)

        last_char = number[8]
        if last_char in ("A", "B", "C"):
            # Already valid
            return number, True
        elif last_char == "8":
            # Convert 8 to B
            return number[:8] + "B", True
        elif last_char == "0":
            # Convert 0 to C
            return number[:8] + "C", True
        else:
            return number, False
    
    # Process number field with certainty
    number_str = get_string_value(formatted_data.get("number", ""))
    processed_number, certainty = process_number(number_str)
    update_field_with_certainty(formatted_data, "number", processed_number, certainty)
    
    # Clear these fields for Philippines passports
    update_field_with_certainty(formatted_data, "mother name", "", True)
    update_field_with_certainty(formatted_data, "father name", "", True)

    return formatted_data

def ethiopia_rules(formatted_data):
    def process_number(number_str):
        if not number_str or not isinstance(number_str, str):
            return ""
        
        number = number_str.strip().upper()
        
        # Length check - must be exactly 9 characters
        if len(number) < 9: return number, False
        # Prefix check - must start with 'EQ' or 'EP'
        if not (number.startswith("EQ") or number.startswith("EP")):
            return number, False
        
        number = correct_ocr_digit_section(number, 2, 9)
        
        # Validate that positions 3-9 are digits
        if not number[2:].isdigit():
            return number, False
        
        return number, True
    
    # Process number field with certainty
    number_str = get_string_value(formatted_data.get("number", ""))
    processed_number, certainty = process_number(number_str)
    update_field_with_certainty(formatted_data, "number", processed_number, certainty)
    
    # Set standard values for Ethiopia passports
    update_field_with_certainty(formatted_data, "place of issue", "ETHIOPIA", True)
    update_field_with_certainty(formatted_data, "country of issue", "ETHIOPIA", True)
    update_field_with_certainty(formatted_data, "mother name", "", True)
    update_field_with_certainty(formatted_data, "father name", "", True)

    return formatted_data

def kenya_rules(formatted_data):
    def process_number(number_str):
        if not number_str or not isinstance(number_str, str):
            return ""
        
        number = number_str.strip().upper()
        
        # Length check - must be exactly 9 characters
        if len(number) < 9: return number, False
        elif len(number) > 9: number = number[:9], False
        
        if not (number.startswith("AK") or number.startswith("BK") or number.startswith("CK")): return number, False

        number = correct_ocr_digit_section(number, 2, 8)
        
        # Validate that positions 3-9 are digits
        if not number[2:].isdigit():
            return number, False
        
        return number, True
    
    number_str = get_string_value(formatted_data.get("number", ""))
    processed_number, certainty = process_number(number_str)
    update_field_with_certainty(formatted_data, "number", processed_number, certainty)
    
    # Process place of issue with fuzzy matching
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    if not place_of_issue:
        update_field_with_certainty(formatted_data, "place of issue", "", False)
    elif fuzz.partial_ratio(place_of_issue, "GOVERNMENT OF KENYA") >= 90:
        update_field_with_certainty(formatted_data, "place of issue", "GOVERNMENT OF KENYA", True)
    elif fuzz.partial_ratio(place_of_issue, "REGISTRAR GENERAL HRE") >= 90:
        update_field_with_certainty(formatted_data, "place of issue", "REGISTRAR GENERAL HRE", True)
    
    # Set standard values for Kenya passports
    update_field_with_certainty(formatted_data, "country of issue", "KENYA", True)
    update_field_with_certainty(formatted_data, "mother name", "", True)
    update_field_with_certainty(formatted_data, "father name", "", True)
    update_field_with_certainty(formatted_data, "middle name", "", True)
    
    return formatted_data

def nepal_rules(formatted_data):
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    if place_of_issue and fuzz.partial_ratio(place_of_issue, "MOFA DEPARTMENT OF PASSPORTS") >= 80:
        update_field_with_certainty(formatted_data, "place of issue", "MOFA", True)
        update_field_with_certainty(formatted_data, "country of issue", "NEPAL", True)
    
    # Process number field
    number = get_string_value(formatted_data.get("number", ""))
    processed_number = number[:9] if len(number) > 9 else number
    processed_number = correct_ocr_digit_section(processed_number, 2, 9)
    
    certainty = processed_number == number
    update_field_with_certainty(formatted_data, "number", processed_number, certainty)

    # Clear these fields for Nepal passports
    update_field_with_certainty(formatted_data, "middle name", "", True)
    update_field_with_certainty(formatted_data, "mother name", "", True)
    update_field_with_certainty(formatted_data, "father name", "", True)
        
    return formatted_data

def sri_lanka_rules(formatted_data):    
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    if place_of_issue and fuzz.partial_ratio(place_of_issue, "AUTHORITY COLOMBO") >= 90:
        update_field_with_certainty(formatted_data, "place of issue", "COLOMBO", True)
        update_field_with_certainty(formatted_data, "country of issue", "SRI LANKA", True)
    
    # Process number field
    number = get_string_value(formatted_data.get("number", ""))
    processed_number = number[:9] if len(number) > 9 else number
    certainty = processed_number == number
    update_field_with_certainty(formatted_data, "number", processed_number, certainty)

    # Clear these fields for Sri Lanka passports
    update_field_with_certainty(formatted_data, "middle name", "", True)
    update_field_with_certainty(formatted_data, "mother name", "", True)
    update_field_with_certainty(formatted_data, "father name", "", True)

    return formatted_data

def india_rules(formatted_data):
    # Process number field
    number = get_string_value(formatted_data.get("number", ""))
    processed_number = number[:9] if len(number) > 9 else number
    certainty = processed_number == number
    update_field_with_certainty(formatted_data, "number", processed_number, certainty)

    mother_name = get_string_value(formatted_data.get("mother name", ""))
    if mother_name:
        processed_mother_name = mother_name.split(" ")[0]
        update_field_with_certainty(formatted_data, "mother name", processed_mother_name)
    
    formatted_data["middle name"] = formatted_data["surname"]
    formatted_data["surname"] = formatted_data["father name"]
 
    return formatted_data

def uganda_rules(formatted_data):
    update_field_with_certainty(formatted_data, "middle name", "", True)
    update_field_with_certainty(formatted_data, "mother name", "", True)
    update_field_with_certainty(formatted_data, "father name", "", True)
    
    return formatted_data

def uzbekistan_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of issue", "UZBEKISTAN", True)
    update_field_with_certainty(formatted_data, "country of issue", "UZBEKISTAN", True)

    return formatted_data

def russia_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of birth", "RUSSIA", True)
    update_field_with_certainty(formatted_data, "place of issue", "RUSSIA", True)
    update_field_with_certainty(formatted_data, "country of issue", "RUSSIA", True)

    return formatted_data

def ukraine_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of issue", "UKRAINE", True)
    update_field_with_certainty(formatted_data, "country of issue", "UKRAINE", True)

    return formatted_data

def kyrgyzstan_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of issue", "KYRGYZSTAN", True)
    update_field_with_certainty(formatted_data, "country of issue", "KYRGYZSTAN", True)

    return formatted_data

def senegal_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of issue", "SENEGAL", True)
    update_field_with_certainty(formatted_data, "country of issue", "SENEGAL", True)

    return formatted_data

def spain_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of issue", "SPAIN", True)
    update_field_with_certainty(formatted_data, "country of issue", "SPAIN", True)

    return formatted_data

def uk_rules(formatted_data):
    update_field_with_certainty(formatted_data, "country of issue", "UNITED KINGDOM", True)

    return formatted_data

def zimbabwe_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of issue", "REGISTRAR GENERAL HRE", True)
    update_field_with_certainty(formatted_data, "country of issue", "ZIMBABWE", True)

    return formatted_data

def lebanon_rules(formatted_data):
    update_field_with_certainty(formatted_data, "place of issue", "GDGS", True)
    update_field_with_certainty(formatted_data, "country of issue", "LEBANON", True)

    return formatted_data

def morocco_rules(formatted_data):
    place_of_birth = get_string_value(formatted_data.get("place of birth", ""))
    if place_of_birth.endswith("MAROC"):
        place_of_birth = place_of_birth[:-6]
        update_field_with_certainty(formatted_data, "place of birth", place_of_birth)
    
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    if "DE" in place_of_issue:
        place_of_issue = place_of_issue.split("DE")[1].strip()
        update_field_with_certainty(formatted_data, "place of issue", place_of_issue)
    
    return formatted_data

def pakistan_rules(formatted_data):
    father_name = get_string_value(formatted_data.get("father name", ""))
    if ', ' in father_name:
        processed_father_name = father_name.split(", ")[1] + " " + father_name.split(", ")[0]
        update_field_with_certainty(formatted_data, "father name", processed_father_name)
    
    formatted_data["middle name"] = formatted_data["surname"]
    formatted_data["surname"] = formatted_data["father name"]
    
    return formatted_data

def iraq_rules(formatted_data):
    surname = get_string_value(formatted_data.get("surname", ""))
    name = get_string_value(formatted_data.get("name", ""))
    if name.endswith(surname):
        name = name[:-len(surname)]
        update_field_with_certainty(formatted_data, "name", name)
    
    return formatted_data

def myanmar_rules(formatted_data):
    full_name = get_string_value(formatted_data.get("mrz_surname", ""))
    name = get_string_value(formatted_data.get("name", ""))
    update_field_with_certainty(formatted_data, "middle name", "", True)
    
    surname = get_string_value(formatted_data.get("surname", ""))
    if full_name:
        names = full_name.split(" ")
        update_field_with_certainty(formatted_data, "surname", names[-1])
        update_field_with_certainty(formatted_data, "name", " ".join(names[:-1]))
    elif surname:
        names = surname.split(" ")
        update_field_with_certainty(formatted_data, "surname", names[-1])
        update_field_with_certainty(formatted_data, "name", " ".join(names[:-1]))
    elif name:
        names = name.split(" ")
        update_field_with_certainty(formatted_data, "surname", names[-1])
        update_field_with_certainty(formatted_data, "name", " ".join(names[:-1]))

    return formatted_data

def country_rules(formatted_data, country):
    if country == "PHL": formatted_data = philippines_rules(formatted_data)
    elif country == "ETH": formatted_data = ethiopia_rules(formatted_data)
    elif country == "KEN": formatted_data = kenya_rules(formatted_data)
    elif country == "NPL": formatted_data = nepal_rules(formatted_data)
    elif country == "LKA": formatted_data = sri_lanka_rules(formatted_data)
    elif country == "UGA": formatted_data = uganda_rules(formatted_data)
    elif country == "IND": formatted_data = india_rules(formatted_data)
    elif country == "UZB": formatted_data = uzbekistan_rules(formatted_data)
    elif country == "RUS": formatted_data = russia_rules(formatted_data)
    elif country == "UKR": formatted_data = ukraine_rules(formatted_data)
    elif country == "KGZ": formatted_data = kyrgyzstan_rules(formatted_data)
    elif country == "SEN": formatted_data = senegal_rules(formatted_data)
    elif country == "ESP": formatted_data = spain_rules(formatted_data)
    elif country == "GBR": formatted_data = uk_rules(formatted_data)
    elif country == "ZWE": formatted_data = zimbabwe_rules(formatted_data)
    elif country == "LBN": formatted_data = lebanon_rules(formatted_data)
    elif country == "MAR": formatted_data = morocco_rules(formatted_data)
    elif country == "PAK": formatted_data = pakistan_rules(formatted_data)
    elif country == "IRQ": formatted_data = iraq_rules(formatted_data)
    elif country == "MMR": formatted_data = myanmar_rules(formatted_data)

    return formatted_data