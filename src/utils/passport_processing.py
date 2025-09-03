import re
from unidecode import unidecode
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import fuzzywuzzy.fuzz as fuzz

from src.utils.country_rules import country_rules, derive_country_of_issue
from src.utils.results_utils import mapper
import pycountry

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

def get_probability(field_value):
    """Extract probability from Regula response metadata"""
    if isinstance(field_value, dict) and 'prob' in field_value:
        return float(field_value['prob'])
    return 0.0

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

def postprocess(json_data):
    """
    Streamlined postprocessing that focuses on domain-specific validation
    while relying on Regula for MRZ, checksums, and basic field extraction.
    """
    formatted_data = dict(json_data)
    
    # Extract or initialize probabilities from Regula
    probabilities = formatted_data.get("probabilities", {})
    
    # === DATE FORMAT STANDARDIZATION ===
    # Regula extracts dates but we need consistent formatting
    PIVOT = datetime.now().year % 100
    TODAY = datetime.now().date()

    def _expand_two_digit_year(yy: int, field: str) -> int:
        """Century expansion that depends on the field."""
        if yy > 1000:
            return yy
        elif field in ["expiry date", "issue date"]:
            return 2000 + yy
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
        """Convert passport dates to 'dd/mm/YYYY' format."""
        if not raw:
            return None

        dt = _parse_dd_mmm_yy(raw, field)

        # Fall back to pandas
        if dt is None:
            try:
                dt = pd.to_datetime(raw, dayfirst=False, errors="raise")
            except Exception:
                return None

        # Field-specific sanity checks
        if field == "birth date":
            if dt.date() > TODAY:
                dt -= relativedelta(years=100)
        elif field == "issue date":
            if dt.date() > TODAY:
                dt -= relativedelta(years=100)
        elif field == "expiry date":
            while dt.date() < TODAY:
                dt += relativedelta(years=100)
            while dt.date() > TODAY + relativedelta(years=25):
                dt -= relativedelta(years=100)

        return dt.strftime("%d/%m/%Y")

    # Apply date formatting
    for date_field in ["issue date", "birth date", "expiry date"]:
        raw_date = get_string_value(formatted_data.get(date_field, ""))
        original_prob = probabilities.get(date_field, 0.0)
        
        smart_date_value = smart_date(raw_date, date_field)
        if smart_date_value:
            update_field_with_probability(formatted_data, probabilities, date_field, smart_date_value, original_prob)
        else:
            # Keep original value but mark lower confidence for malformed dates
            update_field_with_probability(formatted_data, probabilities, date_field, raw_date, original_prob * 0.5)

    # === PLACE OF ISSUE TO COUNTRY OF ISSUE VALIDATION ===
    place_of_issue = get_string_value(formatted_data.get("place of issue", ""))
    place_of_issue_prob = probabilities.get("place of issue", 0.0)
    
    if place_of_issue:
# derive_country_of_issue is already available from country_rules import
        derived_country, city = derive_country_of_issue(place_of_issue)
        if derived_country:
            update_field_with_probability(formatted_data, probabilities, "country of issue", derived_country, place_of_issue_prob)
            # For Uganda, update place to city only
            country = get_string_value(formatted_data.get("country", ""))
            if country == "UGA":
                update_field_with_probability(formatted_data, probabilities, "place of issue", city, place_of_issue_prob)

    # === COUNTRY VALIDATION ===
    country = get_string_value(formatted_data.get("country", ""))
    country_prob = probabilities.get("country", 0.0)
    
    if country not in mapper.values():
        # Try to map from country name to code
        country_title = country.title()
        if country_title in mapper.keys():
            update_field_with_probability(formatted_data, probabilities, "country", mapper[country_title], country_prob)
        else:
            # Mark as uncertain if we can't validate the country
            update_field_with_probability(formatted_data, probabilities, "country", country, country_prob * 0.5)

    # === PLACE OF BIRTH CLEANING ===
    place_of_birth = get_string_value(formatted_data.get("place of birth", ""))
    place_of_birth_prob = probabilities.get("place of birth", 0.0)
    
    if place_of_birth:
        # Remove country suffix if present
        if place_of_birth.endswith(country):
            if len(place_of_birth) > 3 and place_of_birth.endswith(' ' + country):
                cleaned_place = place_of_birth[:-4]
                update_field_with_probability(formatted_data, probabilities, "place of birth", cleaned_place, place_of_birth_prob)
            elif len(place_of_birth) == 3:
                # If it's just the country code, convert to full country name
                invert_country = {v: k for k, v in mapper.items()}
                if country in invert_country:
                    full_country = invert_country[country].upper()
                    update_field_with_probability(formatted_data, probabilities, "place of birth", full_country, place_of_birth_prob)

        # Validate against known birth places
        birth_places = pd.read_csv("static/birth_places.csv")
        birth_places_set = set(birth_places["places"].unique())
        if place_of_birth in birth_places_set:
            # Boost confidence for known valid birth places
            update_field_with_probability(formatted_data, probabilities, "place of birth", place_of_birth, min(1.0, place_of_birth_prob * 1.2))

    # === COUNTRY OF ISSUE VALIDATION ===
    country_of_issue = get_string_value(formatted_data.get("country of issue", ""))
    country_of_issue_prob = probabilities.get("country of issue", 0.0)
    
    if country_of_issue:
        found = False
        # Try fuzzy matching against known countries
        for canonical in mapper.keys():
            canonical_upper = canonical.upper()
            if fuzz.partial_ratio(country_of_issue, canonical_upper) >= 90:
                update_field_with_probability(formatted_data, probabilities, "country of issue", canonical_upper, country_of_issue_prob)
                found = True
                break
        
        if not found:
            # Try pycountry lookup if available
            if pycountry:
                def country_lookup(name: str) -> str | None:
                    try:
                        country_match = pycountry.countries.search_fuzzy(name)[0]
                        return country_match.name
                    except LookupError:
                        return None
                
                lookup_result = country_lookup(country_of_issue)
                if lookup_result:
                    update_field_with_probability(formatted_data, probabilities, "country of issue", lookup_result.upper(), country_of_issue_prob)

    # === APPLY COUNTRY-SPECIFIC RULES ===
    formatted_data = country_rules(formatted_data, country)

    # === STRING FIELD CLEANING ===
    string_fields = [
        "number", "country", "name", "surname", "middle name", "gender",
        "place of birth", "mother name", "father name", "place of issue", "country of issue"
    ]
    
    for field in string_fields:
        if field in formatted_data:
            value = get_string_value(formatted_data[field]).upper()
            if value in ["NAN", "NONE", "NULL", "N/A", "NA"]:
                value = ""
            
            # Clean special characters but preserve spaces
            value = re.sub(r'[^\w\s]', ' ', value)
            value = unidecode(value)
            value = re.sub(r'\s+', ' ', value)
            
            if value:
                formatted_data[field] = value.strip()
            else:
                formatted_data[field] = ""

    # Store probabilities back in the formatted data
    formatted_data["probabilities"] = probabilities
    
    return formatted_data
