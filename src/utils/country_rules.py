from fuzzywuzzy import fuzz
import pandas as pd

def get_string_value(field_value):
    """Extract string value from field or return empty string"""
    if field_value is None:
        return ""
    if hasattr(field_value, '__str__'):
        str_value = str(field_value)
        # Handle "nan", "NaN", "NAN" strings specifically
        if str_value.lower() in ['nan', 'none', 'null', 'n/a', 'na']:
            return ""
        return str_value
    return str(field_value) if field_value else ""

def get_probability(field_name, probabilities):
    """Extract probability for a field from Regula probabilities dict"""
    return probabilities.get(field_name, 0.0)

def update_field_with_probability(formatted_data, probabilities, field_name, new_value, probability=None):
    """Update a field with Regula probability tracking"""
    if new_value is None:
        new_value = ""
    
    formatted_data[field_name] = str(new_value)
    if probability is not None:
        probabilities[field_name] = float(probability)
    # If probability is None, preserve existing probability from Regula
    elif field_name not in probabilities:
        probabilities[field_name] = 0.0

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

def philippines_rules(formatted_data, probabilities):  
    def process_number(number_str):
        if not number_str or not isinstance(number_str, str):
            return "", 0.0
        
        number = number_str.strip().upper()
        
        # Length check - must be exactly 9 characters
        if len(number) < 9: return number, 0.3
        if len(number) > 9:
            return number[:9], 0.5
        
        number = correct_ocr_digit_section(number, 1, 8)

        last_char = number[8]
        if last_char in ("A", "B", "C"):
            # Already valid
            return number, 1.0
        elif last_char == "8":
            # Convert 8 to B
            return number[:8] + "B", 0.8
        elif last_char == "0":
            # Convert 0 to C
            return number[:8] + "C", 0.8
        else:
            return number, 0.3
    
    # Process number field with probability
    number_str = get_string_value(formatted_data.get("number", ""))
    original_prob = get_probability("number", probabilities)
    processed_number, validation_prob = process_number(number_str)
    # Use the minimum of original extraction probability and validation probability
    final_prob = min(original_prob, validation_prob) if original_prob > 0 else validation_prob
    update_field_with_probability(formatted_data, probabilities, "number", processed_number, final_prob)
    
    # Clear these fields for Philippines passports (high confidence)
    update_field_with_probability(formatted_data, probabilities, "mother name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "father name", "", 1.0)

    return formatted_data

def ethiopia_rules(formatted_data, probabilities):
    def process_number(number_str):
        if not number_str or not isinstance(number_str, str):
            return "", 0.0
        
        number = number_str.strip().upper()
        
        # Length check - must be exactly 9 characters
        if len(number) < 9: return number, 0.3
        # Prefix check - must start with 'EQ' or 'EP'
        if not (number.startswith("EQ") or number.startswith("EP")):
            return number, 0.2
        
        number = correct_ocr_digit_section(number, 2, 9)
        
        # Validate that positions 3-9 are digits
        if not number[2:].isdigit():
            return number, 0.4
        
        return number, 1.0
    
    # Process number field with probability
    number_str = get_string_value(formatted_data.get("number", ""))
    original_prob = get_probability("number", probabilities)
    processed_number, validation_prob = process_number(number_str)
    final_prob = min(original_prob, validation_prob) if original_prob > 0 else validation_prob
    update_field_with_probability(formatted_data, probabilities, "number", processed_number, final_prob)
    
    # Set standard values for Ethiopia passports
    update_field_with_probability(formatted_data, probabilities, "place of issue", "ETHIOPIA", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "ETHIOPIA", 1.0)
    update_field_with_probability(formatted_data, probabilities, "mother name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "father name", "", 1.0)

    return formatted_data

def kenya_rules(formatted_data, probabilities):
    def process_number(number_str):
        if not number_str or not isinstance(number_str, str):
            return "", 0.0
        
        number = number_str.strip().upper()
        
        # Length check - must be exactly 9 characters
        if len(number) < 9: return number, 0.3
        elif len(number) > 9: return number[:9], 0.5
        
        if not (number.startswith("AK") or number.startswith("BK") or number.startswith("CK")): 
            return number, 0.2

        number = correct_ocr_digit_section(number, 2, 8)
        
        # Validate that positions 3-9 are digits
        if not number[2:].isdigit():
            return number, 0.4
        
        return number, 1.0
    
    number_str = get_string_value(formatted_data.get("number", ""))
    original_prob = get_probability("number", probabilities)
    processed_number, validation_prob = process_number(number_str)
    final_prob = min(original_prob, validation_prob) if original_prob > 0 else validation_prob
    update_field_with_probability(formatted_data, probabilities, "number", processed_number, final_prob)
    
    # Process place of issue with fuzzy matching
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    
    if not place_of_issue:
        update_field_with_probability(formatted_data, probabilities, "place of issue", "", 0.0)
    elif fuzz.partial_ratio(place_of_issue, "GOVERNMENT OF KENYA") >= 90:
        update_field_with_probability(formatted_data, probabilities, "place of issue", "GOVERNMENT OF KENYA", 1.0)
    elif fuzz.partial_ratio(place_of_issue, "REGISTRAR GENERAL HRE") >= 90:
        update_field_with_probability(formatted_data, probabilities, "place of issue", "REGISTRAR GENERAL HRE", 1.0)
    
    # Set standard values for Kenya passports
    update_field_with_probability(formatted_data, probabilities, "country of issue", "KENYA", 1.0)
    update_field_with_probability(formatted_data, probabilities, "mother name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "father name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "middle name", "", 1.0)
    
    return formatted_data

def nepal_rules(formatted_data, probabilities):
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    
    if place_of_issue and fuzz.partial_ratio(place_of_issue, "MOFA DEPARTMENT OF PASSPORTS") >= 80:
        update_field_with_probability(formatted_data, probabilities, "place of issue", "MOFA", 1.0)
        update_field_with_probability(formatted_data, probabilities, "country of issue", "NEPAL", 1.0)
    
    # Process number field
    number = get_string_value(formatted_data.get("number", ""))
    original_prob = get_probability("number", probabilities)
    processed_number = number[:9] if len(number) > 9 else number
    processed_number = correct_ocr_digit_section(processed_number, 2, 9)
    
    # Adjust probability based on whether processing changed the number
    if processed_number == number:
        final_prob = original_prob
    else:
        final_prob = max(0.7, original_prob * 0.8) if original_prob > 0 else 0.7
    
    update_field_with_probability(formatted_data, probabilities, "number", processed_number, final_prob)

    # Clear these fields for Nepal passports
    update_field_with_probability(formatted_data, probabilities, "middle name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "mother name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "father name", "", 1.0)
        
    return formatted_data

def sri_lanka_rules(formatted_data, probabilities):    
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    if place_of_issue and fuzz.partial_ratio(place_of_issue, "AUTHORITY COLOMBO") >= 90:
        update_field_with_probability(formatted_data, probabilities, "place of issue", "COLOMBO", 1.0)
        update_field_with_probability(formatted_data, probabilities, "country of issue", "SRI LANKA", 1.0)
    
    # Process number field
    number = get_string_value(formatted_data.get("number", ""))
    original_prob = get_probability("number", probabilities)
    processed_number = number[:9] if len(number) > 9 else number
    
    # Adjust probability based on whether processing changed the number
    if processed_number == number:
        final_prob = original_prob
    else:
        final_prob = max(0.7, original_prob * 0.8) if original_prob > 0 else 0.7
        
    update_field_with_probability(formatted_data, probabilities, "number", processed_number, final_prob)

    # Clear these fields for Sri Lanka passports
    update_field_with_probability(formatted_data, probabilities, "middle name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "mother name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "father name", "", 1.0)

    return formatted_data

def india_rules(formatted_data, probabilities):
    # Process number field
    number = get_string_value(formatted_data.get("number", ""))
    original_prob = get_probability("number", probabilities)
    processed_number = number[:9] if len(number) > 9 else number
    
    # Adjust probability based on whether processing changed the number
    if processed_number == number:
        final_prob = original_prob
    else:
        final_prob = max(0.7, original_prob * 0.8) if original_prob > 0 else 0.7
        
    update_field_with_probability(formatted_data, probabilities, "number", processed_number, final_prob)

    mother_name = get_string_value(formatted_data.get("mother name", ""))
    mother_prob = get_probability("mother name", probabilities)
    if mother_name:
        processed_mother_name = mother_name.split(" ")[0]
        update_field_with_probability(formatted_data, probabilities, "mother name", processed_mother_name, mother_prob)
    
    # Handle name field rearrangement for India
    surname_val = formatted_data.get("surname", "")
    father_name_val = formatted_data.get("father name", "")
    
    formatted_data["middle name"] = surname_val
    formatted_data["surname"] = father_name_val
    
    # Transfer probabilities for rearranged fields
    surname_prob = get_probability("surname", probabilities)
    father_prob = get_probability("father name", probabilities)
    
    probabilities["middle name"] = surname_prob
    probabilities["surname"] = father_prob
 
    return formatted_data

def uganda_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "middle name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "mother name", "", 1.0)
    update_field_with_probability(formatted_data, probabilities, "father name", "", 1.0)
    
    return formatted_data

def uzbekistan_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of issue", "UZBEKISTAN", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "UZBEKISTAN", 1.0)

    return formatted_data

def russia_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of birth", "RUSSIA", 1.0)
    update_field_with_probability(formatted_data, probabilities, "place of issue", "RUSSIA", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "RUSSIA", 1.0)

    return formatted_data

def ukraine_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of issue", "UKRAINE", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "UKRAINE", 1.0)

    return formatted_data

def kyrgyzstan_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of issue", "KYRGYZSTAN", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "KYRGYZSTAN", 1.0)

    return formatted_data

def senegal_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of issue", "SENEGAL", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "SENEGAL", 1.0)

    return formatted_data

def spain_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of issue", "SPAIN", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "SPAIN", 1.0)

    return formatted_data

def uk_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "country of issue", "UNITED KINGDOM", 1.0)

    return formatted_data

def zimbabwe_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of issue", "REGISTRAR GENERAL HRE", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "ZIMBABWE", 1.0)

    return formatted_data

def lebanon_rules(formatted_data, probabilities):
    update_field_with_probability(formatted_data, probabilities, "place of issue", "GDGS", 1.0)
    update_field_with_probability(formatted_data, probabilities, "country of issue", "LEBANON", 1.0)

    return formatted_data

def morocco_rules(formatted_data, probabilities):
    place_of_birth = get_string_value(formatted_data.get("place of birth", ""))
    birth_prob = get_probability("place of birth", probabilities)
    
    if place_of_birth.endswith("MAROC"):
        cleaned_place = place_of_birth[:-6]
        update_field_with_probability(formatted_data, probabilities, "place of birth", cleaned_place, birth_prob)
    
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    issue_prob = get_probability("place of issue", probabilities)
    
    if "DE" in place_of_issue:
        cleaned_issue = place_of_issue.split("DE")[1].strip()
        update_field_with_probability(formatted_data, probabilities, "place of issue", cleaned_issue, issue_prob)
    
    return formatted_data

def pakistan_rules(formatted_data, probabilities):
    father_name = get_string_value(formatted_data.get("father name", ""))
    father_prob = get_probability("father name", probabilities)
    
    if ', ' in father_name:
        processed_father_name = father_name.split(", ")[1] + " " + father_name.split(", ")[0]
        update_field_with_probability(formatted_data, probabilities, "father name", processed_father_name, father_prob)
    
    # Handle name field rearrangement for Pakistan
    surname_val = formatted_data.get("surname", "")
    father_name_val = formatted_data.get("father name", "")
    
    formatted_data["middle name"] = surname_val
    formatted_data["surname"] = father_name_val
    
    # Transfer probabilities for rearranged fields
    surname_prob = get_probability("surname", probabilities)
    updated_father_prob = get_probability("father name", probabilities)
    
    probabilities["middle name"] = surname_prob
    probabilities["surname"] = updated_father_prob
    
    return formatted_data

def iraq_rules(formatted_data, probabilities):
    surname = get_string_value(formatted_data.get("surname", ""))
    name = get_string_value(formatted_data.get("name", ""))
    name_prob = get_probability("name", probabilities)
    
    if name.endswith(surname):
        cleaned_name = name[:-len(surname)]
        update_field_with_probability(formatted_data, probabilities, "name", cleaned_name, name_prob)
    
    return formatted_data

def myanmar_rules(formatted_data, probabilities):
    full_name = get_string_value(formatted_data.get("mrz_surname", ""))
    name = get_string_value(formatted_data.get("name", ""))
    surname = get_string_value(formatted_data.get("surname", ""))
    
    update_field_with_probability(formatted_data, probabilities, "middle name", "", 1.0)
    
    name_prob = get_probability("name", probabilities)
    surname_prob = get_probability("surname", probabilities)
    
    if full_name:
        names = full_name.split(" ")
        if len(names) > 1:
            update_field_with_probability(formatted_data, probabilities, "surname", names[-1], surname_prob)
            update_field_with_probability(formatted_data, probabilities, "name", " ".join(names[:-1]), name_prob)
    elif surname:
        names = surname.split(" ")
        if len(names) > 1:
            update_field_with_probability(formatted_data, probabilities, "surname", names[-1], surname_prob)
            update_field_with_probability(formatted_data, probabilities, "name", " ".join(names[:-1]), name_prob)
    elif name:
        names = name.split(" ")
        if len(names) > 1:
            update_field_with_probability(formatted_data, probabilities, "surname", names[-1], surname_prob)
            update_field_with_probability(formatted_data, probabilities, "name", " ".join(names[:-1]), name_prob)

    return formatted_data

def country_rules(formatted_data, country):
    """
    Apply country-specific validation rules using Regula probability tracking.
    
    Args:
        formatted_data: Dict containing extracted passport data
        country: Three-letter country code
        
    Returns:
        Updated formatted_data with probabilities preserved
    """
    # Extract probabilities dict, create if not present
    probabilities = formatted_data.get("probabilities", {})
    
    if country == "PHL": formatted_data = philippines_rules(formatted_data, probabilities)
    elif country == "ETH": formatted_data = ethiopia_rules(formatted_data, probabilities)
    elif country == "KEN": formatted_data = kenya_rules(formatted_data, probabilities)
    elif country == "NPL": formatted_data = nepal_rules(formatted_data, probabilities)
    elif country == "LKA": formatted_data = sri_lanka_rules(formatted_data, probabilities)
    elif country == "UGA": formatted_data = uganda_rules(formatted_data, probabilities)
    elif country == "IND": formatted_data = india_rules(formatted_data, probabilities)
    elif country == "UZB": formatted_data = uzbekistan_rules(formatted_data, probabilities)
    elif country == "RUS": formatted_data = russia_rules(formatted_data, probabilities)
    elif country == "UKR": formatted_data = ukraine_rules(formatted_data, probabilities)
    elif country == "KGZ": formatted_data = kyrgyzstan_rules(formatted_data, probabilities)
    elif country == "SEN": formatted_data = senegal_rules(formatted_data, probabilities)
    elif country == "ESP": formatted_data = spain_rules(formatted_data, probabilities)
    elif country == "GBR": formatted_data = uk_rules(formatted_data, probabilities)
    elif country == "ZWE": formatted_data = zimbabwe_rules(formatted_data, probabilities)
    elif country == "LBN": formatted_data = lebanon_rules(formatted_data, probabilities)
    elif country == "MAR": formatted_data = morocco_rules(formatted_data, probabilities)
    elif country == "PAK": formatted_data = pakistan_rules(formatted_data, probabilities)
    elif country == "IRQ": formatted_data = iraq_rules(formatted_data, probabilities)
    elif country == "MMR": formatted_data = myanmar_rules(formatted_data, probabilities)

    # Ensure probabilities are stored back in the formatted_data
    formatted_data["probabilities"] = probabilities
    
    return formatted_data