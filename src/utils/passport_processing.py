import re
from unidecode import unidecode
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import fuzzywuzzy.fuzz as fuzz

from src.utils.country_rules import *
from src.utils.results_utils import mapper
import pycountry

string_fields = [
    "number", "country", "name", "surname", "middle name", "gender",
    "place of birth", "mother name", "father name", "place of issue", "country of issue",
    "mrz_surname", "mrz_name", "mrz_date_of_birth", "mrz_date_of_expiry", "mrz_gender"
]

def valid_mrz_one(mrz_line1):
    """Check if there are more than occurence of '<<' before a letter"""
    matches = re.findall(r'<<[A-Z]', mrz_line1)
    return len(matches) <= 1

def format_string_fields(formatted_data):
    for field in string_fields:
        if field in formatted_data:
            value = get_string_value(formatted_data[field]).upper()
            if value in ["NAN", "NONE", "NULL", "N/A", "NA"]:
                value = ""
            value = re.sub(r'[^\w\s]', ' ', value)

            value = unidecode(value)
            value = re.sub(r'\s+', ' ', value)
            if value:
                update_field_with_certainty(formatted_data, field, value.strip())
            else:
                update_field_with_certainty(formatted_data, field, "")
    return formatted_data

def postprocess(json_data):
    formatted_data = dict(json_data)

    def calculate_checksum(input_string):
        weights = [7, 3, 1]
        total = 0
        for i, char in enumerate(input_string):
            if char.isdigit():
                value = int(char)
            elif char == '<':
                value = 0
            else:
                value = ord(char) - 55  # A=10, B=11, etc.
            total += value * weights[i % 3]
        return total % 10
    
    mrz_line1 = get_string_value(formatted_data.get("mrzLine1", ""))
    mrz_line2 = get_string_value(formatted_data.get("mrzLine2", ""))
    country = get_string_value(formatted_data.get("country", ""))

    if country not in mapper.values():
        update_field_with_certainty(formatted_data, "country", country, False)
        country = country.title()
        if country in mapper.keys():
            country = mapper[country]
            update_field_with_certainty(formatted_data, "country", country, True)
    else:
        update_field_with_certainty(formatted_data, "country", country, True)

    if not isinstance(mrz_line1, str): mrz_line1 = ""
    if not isinstance(mrz_line2, str): mrz_line2 = ""

    mrz_line1 = mrz_line1.strip()
    mrz_line2 = mrz_line2.strip()

    mrz_surname = get_string_value(formatted_data.get("mrz_surname", ""))
    mrz_name = get_string_value(formatted_data.get("mrz_name", ""))

    if valid_mrz_one(mrz_line1) and (mrz_surname or mrz_name) and country not in ["UZB"]:
        ocr_surname = get_string_value(formatted_data.get("surname", ""))
        ocr_name = get_string_value(formatted_data.get("name", ""))

        if country in ["LKA", "IND", "MDG"]:
            if mrz_surname:
                clean_surname = unidecode(re.sub(r'[^\w\s]', '', mrz_surname).upper().replace(" ", ""))
                clean_original = unidecode(re.sub(r'[^\w\s]', '', ocr_surname).upper().replace(" ", ""))
                if clean_surname != clean_original and len(clean_surname) >= len(clean_original):
                    mrz_surname_certainty = get_certainty(formatted_data.get("mrz_surname", ""))
                    ocr_surname_certainty = get_certainty(formatted_data.get("surname", ""))
                    if mrz_surname_certainty == True or ocr_surname_certainty == False:
                        update_field_with_certainty(formatted_data, "surname", mrz_surname, False)
                    else:
                        update_field_with_certainty(formatted_data, "surname", ocr_surname, False)
            
            if mrz_name:
                clean_mrz = re.sub(r'[^\w\s]', '', mrz_name).upper().replace(" ", "")
                clean_original = re.sub(r'[^\w\s]', '', ocr_name).upper().replace(" ", "")
                ocr_name_certainty = get_certainty(formatted_data.get("name", ""))
                mrz_name_certainty = get_certainty(formatted_data.get("mrz_name", ""))

                if clean_original != clean_mrz and len(clean_original) <= len(clean_mrz):
                    if mrz_name_certainty or ocr_name_certainty == False:
                        update_field_with_certainty(formatted_data, "name", mrz_name, False)
                    else:
                        update_field_with_certainty(formatted_data, "name", ocr_name, False)
        
        else:
            if mrz_surname:
                clean_surname = unidecode(re.sub(r'[^\w\s]', '', mrz_surname).upper().replace(" ", ""))
                clean_original = unidecode(re.sub(r'[^\w\s]', '', ocr_surname).upper().replace(" ", ""))
                if clean_surname != clean_original:
                    mrz_surname_certainty = get_certainty(formatted_data.get("mrz_surname", ""))
                    ocr_surname_certainty = get_certainty(formatted_data.get("surname", ""))
                    if mrz_surname_certainty == True or ocr_surname_certainty == False:
                        update_field_with_certainty(formatted_data, "surname", mrz_surname, False)
                    else:
                        update_field_with_certainty(formatted_data, "surname", ocr_surname, False)
            
            if mrz_name:
                clean_mrz = re.sub(r'[^\w\s]', '', mrz_name).upper().replace(" ", "")
                clean_original = re.sub(r'[^\w\s]', '', ocr_name).upper().replace(" ", "")
                ocr_name_certainty = get_certainty(formatted_data.get("name", ""))
                mrz_name_certainty = get_certainty(formatted_data.get("mrz_name", ""))

                if clean_original != clean_mrz:
                    if mrz_name_certainty or ocr_name_certainty == False:
                        update_field_with_certainty(formatted_data, "name", mrz_name, False)
                    else:
                        update_field_with_certainty(formatted_data, "name", ocr_name, False)
    

    if formatted_data.get("surname", "").startswith(country) and country*2 not in mrz_line1:
        update_field_with_certainty(formatted_data, "surname", formatted_data.get("surname", "")[3:], False)
    

    if len(mrz_line2) >= 10:
        doc_number = mrz_line2[:9].replace("<", "").strip()
        doc_number_check = mrz_line2[9]
        if doc_number and doc_number_check.isdigit():
            calculated_check = str(calculate_checksum(doc_number.ljust(9, '<')))
            if calculated_check == doc_number_check and doc_number != formatted_data.get("number", ""):
                update_field_with_certainty(formatted_data, "number", doc_number, False)


    PIVOT = datetime.now().year % 100          # 25 → for 2025
    TODAY  = datetime.now().date()

    def _expand_two_digit_year(yy: int, field: str) -> int:
        """
        Century expansion that depends on the field.
        birth / issue : pivot rule (<= pivot → 2000s, > pivot → 1900s)
        expiry        : start in 2000s and adjust later if needed
        """
        if yy > 1000:
            return yy
        elif field in ["expiry date", "issue date"]:
            return 2000 + yy            # 27 → 2027, 03 → 2003 (initial guess)
        else:
            return 1900 + yy if yy > PIVOT else 2000 + yy

    _dd_mmm_yy = re.compile(r"^\s*(\d{1,2})(?:\s+|\/)(\w+)\s*(?:\s*|\/)\s*(\w*)(?:\s+|\/)(\d{2,4})\s*$", re.I)

    def _parse_dd_mmm_yy(s: str, field: str):
        m = _dd_mmm_yy.match(unidecode(s))
        if not m:
            return None
        day, mon, mon_2, yy = m.groups()
        
        yyyy = _expand_two_digit_year(int(yy), field)
        try: 
            return datetime.strptime(f"{day} {mon.title()} {yyyy}", "%d %b %Y")
        except:
            try: 
                return datetime.strptime(f"{day} {mon_2.title()} {yyyy}", "%d %b %Y")
            except:
                return None

    def smart_date(raw: str, field: str) -> str | None:
        """
        Convert passport dates to 'dd/mm/YYYY'.
        field ∈ {'birth date', 'issue date', 'expiry date'}
        """
        if not raw:
            return None

        dt = _parse_dd_mmm_yy(raw, field)

        # 2️⃣ otherwise fall back to pandas
        if dt is None:
            try:
                dt = pd.to_datetime(raw, dayfirst=True, errors="raise")
            except Exception:
                return None

        # 3️⃣ field-specific sanity
        if field == "birth date":
            if dt.date() > TODAY:                       # birth in the future? subtract a century
                dt -= relativedelta(years=100)

        elif field == "issue date":
            if dt.date() > TODAY:                       # issue in the future? subtract a century
                dt -= relativedelta(years=100)

        elif field == "expiry date":
            # make sure expiry lies within the next 0-15 years
            while dt.date() < TODAY:                    # already expired → add a century
                dt += relativedelta(years=100)
            while dt.date() > TODAY + relativedelta(years=25):  # implausibly far → minus a century
                dt -= relativedelta(years=100)

        return dt.strftime("%d/%m/%Y")

    for k in ["issue date", "birth date", "expiry date"]:
        smart_date_value = smart_date(formatted_data.get(k, ""), k)
        if smart_date_value:
            update_field_with_certainty(formatted_data, k, smart_date_value)
        else:
            old_value = get_string_value(formatted_data.get(k, ""))
            update_field_with_certainty(formatted_data, k, old_value, False)

    mrz_gender = get_string_value(formatted_data.get("mrz_gender", ""))
    if mrz_gender and mrz_gender in ["M", "F"]:
        update_field_with_certainty(formatted_data, "gender", mrz_gender)
    
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    place_of_issue_certainty = get_certainty(formatted_data.get("place of issue", ""))
    if place_of_issue:
        from src.utils.country_rules import derive_country_of_issue
        derived_country, city = derive_country_of_issue(place_of_issue)
        if derived_country:
            update_field_with_certainty(formatted_data, "country of issue", derived_country, place_of_issue_certainty)
            if country == "UGA":
                update_field_with_certainty(formatted_data, "place of issue", city)

    invert_country = {v: k for k, v in mapper.items()}
    place_of_birth = get_string_value(formatted_data.get("place of birth", ""))
    if place_of_birth.endswith(country):
        if len(place_of_birth) > 3 and place_of_birth.endswith(' ' + country):
            update_field_with_certainty(formatted_data, "place of birth", place_of_birth[:-4])
        elif len(place_of_birth) == 3:
            update_field_with_certainty(formatted_data, "place of birth", invert_country[country].upper())

    def country_lookup(name: str) -> str | None:
        try:
            # pycountry returns a list of matches ranked by Levenshtein distance
            country = pycountry.countries.search_fuzzy(name)[0]
            return country.name
        except LookupError:
            return None

    country_of_issue = get_string_value(formatted_data.get("country of issue", ""))
    found = False
    for canonical in mapper.keys():
        canonical = canonical.upper()
        if fuzz.partial_ratio(country_of_issue, canonical) >= 90:
            update_field_with_certainty(formatted_data, "country of issue", canonical)
            found = True
            break
    
    if not found:
        lookup = country_lookup(country_of_issue)
        if lookup:
            update_field_with_certainty(formatted_data, "country of issue", lookup.upper())

    formatted_data = country_rules(formatted_data, country)

    try:
        from src.passport_extraction import CertainField
        for key, value in formatted_data.items():
            if value is None:
                formatted_data[key] = CertainField("", False)
            elif not isinstance(value, CertainField):
                formatted_data[key] = CertainField(str(value) if value is not None else "", False)
    except ImportError:
        for key, value in formatted_data.items():
            if value is None:
                formatted_data[key] = ""


    formatted_data = format_string_fields(formatted_data)

    place_of_birth = get_string_value(formatted_data.get("place of birth", ""))
    birth_places = pd.read_csv("static/birth_places.csv")
    birth_places = set(birth_places["places"].unique())
    if place_of_birth in birth_places:
        update_field_with_certainty(formatted_data, "place of birth", place_of_birth, True)

    return formatted_data