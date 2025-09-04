# Regula Validation & Postprocessing Flow

This document details the step-by-step flow of how passport data is processed through our Regula validation and postprocessing pipeline.

## 🔄 Overview

```
Regula Raw Response → Field Mapping → Postprocessing → Country Rules → Final Output
     (0-100 probs)    (normalize)     (validate)      (country      (0.0-1.0 probs)
                       (extract)       (standardize)    specific)
```

## 📊 Data Flow Steps

### Step 1: Regula Raw Response
```json
{
  "ContainerList": {
    "List": [
      {
        "Text": {
          "fieldList": [
            {
              "fieldName": "Given Names",
              "valueList": [
                {
                  "source": "VISUAL",
                  "value": "ELAINE",
                  "probability": 97,  // Raw 0-100 scale
                  "originalValue": "ELAINE"
                }
              ]
            }
          ]
        }
      }
    ]
  }
}
```

### Step 2: Field Mapping & Probability Normalization
**File**: `src/adapters/regula_mapper.py`

#### 2.1 Build Field Index
```python
def _build_field_index(raw):
    # Extract all fields from Regula response
    # Group by field name and source (MRZ vs VISUAL)
    # Normalize probabilities: 0-100 → 0.0-1.0
    prob = float(v.get("probability") or 0) / 100.0
```

#### 2.2 Choose Best Values
```python
def _choose_value(idx, aliases, prefer):
    # Apply source preference rules:
    # - passport number: prefer MRZ
    # - birth date: prefer MRZ  
    # - issue date: prefer VISUAL
    # - everything else: highest probability
    return best_value, source, probability
```

#### 2.3 Universal Format Output
```python
{
    "number": "P7264272A",
    "name": "ELAINE", 
    "surname": "SARGUIT",
    "birth date": "1974-03-18",
    "probabilities": {
        "number": 0.97,      # Normalized 97/100
        "name": 0.97,        # Normalized 97/100
        "surname": 1.0,      # Normalized 100/100
        "birth date": 1.0
    }
}
```

### Step 3: Core Postprocessing
**File**: `src/utils/passport_processing.py`

#### 3.1 Date Format Standardization
```python
def smart_date(raw: str, field: str) -> str:
    # Input: Various formats ("18 Mar 1974", "1974-03-18", etc.)
    # Output: Standardized "dd/mm/YYYY" format
    
    # Century expansion logic:
    # - birth/issue dates: pivot rule (25 → 1925 vs 2025)
    # - expiry dates: ensure future date within 25 years
    
    return "18/03/1974"  # Always dd/mm/YYYY
```

**Probability Handling**: Preserves original Regula confidence. Reduces by 50% if date parsing fails.

#### 3.2 Country Validation & Mapping
```python
def validate_country(country, probabilities):
    # Check if country is valid 3-letter code
    if country not in mapper.values():
        # Try mapping from name to code
        if country.title() in mapper.keys():
            country = mapper[country.title()]
            # Keep original probability
        else:
            # Reduce confidence for unknown countries
            probability *= 0.5
```

#### 3.3 Place of Issue → Country of Issue
```python
def derive_country_from_place(place_of_issue):
    # Smart mapping using fuzzy matching
    # "PE KUWAIT" → "KUWAIT"
    # "MOFA DEPARTMENT" → "NEPAL"
    
    city_country_map = load_city_country_mapping()
    best_match = fuzzy_match(place_of_issue, city_country_map)
    
    if match_score >= 90:
        return country, city
```

**Probability Handling**: Inherits probability from place of issue field.

#### 3.4 Place of Birth Cleaning
```python
def clean_place_of_birth(place, country):
    # Remove country suffixes
    # "BUGUEY CAGAYAN PHL" → "BUGUEY CAGAYAN"
    
    # Validate against known places
    if place in known_birth_places:
        probability = min(1.0, original_prob * 1.2)  # Boost confidence
```

#### 3.5 String Field Cleaning
```python
def clean_string_fields(formatted_data):
    # For all text fields:
    # 1. Remove special characters (keep spaces)
    # 2. Apply unidecode (accents → ASCII)
    # 3. Normalize whitespace
    # 4. Convert to uppercase
    
    # Probability: Preserved from original extraction
```

### Step 4: Country-Specific Rules
**File**: `src/utils/country_rules.py`

#### 4.1 Philippines Rules (PHL)
```python
def philippines_rules(data, probabilities):
    # Document number validation
    def validate_number(number):
        if len(number) == 9:
            if last_char in ("A", "B", "C"):
                return number, 1.0        # Perfect format
            elif last_char == "8":
                return number[:-1] + "B", 0.8  # OCR correction
            elif last_char == "0": 
                return number[:-1] + "C", 0.8  # OCR correction
        return number, 0.3  # Invalid format
    
    # Clear family fields (not in Philippines passports)
    probabilities["mother name"] = 1.0  # High confidence in clearing
    probabilities["father name"] = 1.0
```

#### 4.2 Kenya Rules (KEN)
```python
def kenya_rules(data, probabilities):
    # Prefix validation
    if number.startswith(("AK", "BK", "CK")) and number[2:].isdigit():
        validation_prob = 1.0
    else:
        validation_prob = 0.2
    
    # Place of issue fuzzy matching
    if fuzzy_match(place, "GOVERNMENT OF KENYA") >= 90:
        place = "GOVERNMENT OF KENYA"
        probability = 1.0  # High confidence in standardization
```

#### 4.3 India Rules (IND)
```python
def india_rules(data, probabilities):
    # Name field rearrangement (India-specific format)
    # surname → middle name
    # father name → surname
    
    # Transfer probabilities correctly
    probabilities["middle name"] = probabilities["surname"]
    probabilities["surname"] = probabilities["father name"]
    
    # Mother name processing (first word only)
    if mother_name:
        processed = mother_name.split()[0] 
        # Keep original probability
```

#### 4.4 Probability Combination Logic
```python
def combine_probabilities(original_prob, validation_prob):
    # Conservative approach: use minimum of both
    if original_prob > 0:
        return min(original_prob, validation_prob)
    else:
        return validation_prob
```

### Step 5: Final Output Structure
```python
{
    # Cleaned and validated field values
    "number": "P7264272A",
    "country": "PHL", 
    "name": "ELAINE",
    "surname": "SARGUIT",
    "birth date": "18/03/1974",  # Standardized format
    "place of issue": "PE KUWAIT",
    "country of issue": "KUWAIT",  # Derived from place
    
    # Probability tracking for each field
    "probabilities": {
        "number": 0.97,           # Regula confidence
        "country": 1.0,           # Country validation boosted
        "name": 0.97,             # Preserved from Regula
        "surname": 1.0,           # Preserved from Regula  
        "birth date": 1.0,        # Date parsing successful
        "place of issue": 1.0,    # Preserved from Regula
        "country of issue": 1.0   # Inherited from place validation
    }
}
```

## 🎯 Probability Management Rules

### 1. Preservation Principle
- **Default**: Preserve original Regula confidence scores
- **Enhancement**: Boost confidence for validated data (known places, correct formats)
- **Reduction**: Lower confidence for validation failures or unknown data

### 2. Source Preference Rules
```python
PREFER_SOURCE = {
    "number": "MRZ",           # MRZ more reliable for numbers
    "birth date": "MRZ",       # MRZ dates are standardized
    "expiry date": "MRZ",      # MRZ dates are standardized
    "issue date": "VISUAL",    # MRZ doesn't contain issue dates
    # Default: VISUAL (higher quality text recognition)
}
```

### 3. Probability Adjustment Strategies

| Scenario | Adjustment | Reasoning |
|----------|------------|-----------|
| Valid country code | Keep original | Already validated by Regula |
| Country name mapping | Keep original | Successful normalization |
| Unknown country | × 0.5 | Needs human review |
| Date parsing success | Keep original | Format standardized |
| Date parsing failure | × 0.5 | Malformed date data |
| Country rule validation | min(original, validation) | Conservative approach |
| Known birth place | × 1.2 (max 1.0) | Boost valid places |
| OCR character correction | 0.8 | High confidence in correction |
| Format validation failure | 0.3 | Low confidence, needs review |

## 🔧 Error Handling & Edge Cases

### 1. Missing Fields
```python
if field_name not in probabilities:
    probabilities[field_name] = 0.0  # Unknown confidence
```

### 2. Invalid Probability Values
```python
try:
    prob = float(regula_prob) / 100.0
except (ValueError, TypeError):
    prob = 0.0  # Default to no confidence
```

### 3. Country Rule Failures
```python
try:
    formatted_data = country_rules(data, country)
except Exception:
    # Keep original data, log error
    # Don't fail entire processing
```

### 4. Postprocessing Failures
```python
def update_field_with_probability(data, probs, field, value, prob=None):
    data[field] = str(value) if value else ""
    if prob is not None:
        probs[field] = float(prob)
    # If prob is None, preserve existing probability
```

## 🚀 Performance Optimizations

### 1. Single Pass Processing
- All validation rules applied in one iteration
- Probabilities updated in-place during processing
- No redundant field lookups

### 2. Efficient Data Structures
- Dictionary-based field access
- Pre-loaded mapping tables (countries, cities, birth places)
- Cached compiled regex patterns for date parsing

### 3. Lazy Loading
- Optional dependencies (pycountry) loaded on demand
- Large reference files loaded once and cached

## 🧪 Validation Quality Metrics

### Input Quality (from Regula)
- **High**: 0.9-1.0 (clear MRZ, good OCR)
- **Medium**: 0.7-0.89 (minor OCR issues)
- **Low**: 0.5-0.69 (validation concerns)
- **Poor**: 0.0-0.49 (needs human review)

### Output Quality (after processing)
- **Enhanced**: Higher confidence after validation
- **Preserved**: Same confidence as input
- **Reduced**: Lower confidence due to validation failures
- **Derived**: New confidence for derived fields

This validation flow ensures that we maximize the value of Regula's OCR capabilities while adding domain-specific intelligence and maintaining transparency through probability tracking.
