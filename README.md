# Regula Document Reader for Passport Processing

A comprehensive passport information extraction system using Regula's OCR technology with domain-specific validation and probability tracking.

## 🚀 Overview

This system processes passport images using Regula's document reader, applies country-specific validation rules, and outputs structured data with confidence scores. It's specifically designed for processing maid passport data with robust postprocessing and Google Sheets integration.

## 📋 Features

- **Regula OCR Integration**: Advanced passport field extraction with MRZ validation
- **Probability Tracking**: Regula confidence scores (0.0-1.0) for each extracted field
- **Country-Specific Rules**: Validation logic for 20+ countries (Philippines, Kenya, India, etc.)
- **Smart Postprocessing**: Date standardization, place validation, country mapping
- **Google Sheets Upload**: Automated results upload with probability scores
- **Robust Error Handling**: Graceful failure handling and debugging output

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Passport       │    │     Regula      │    │   Universal     │
│  Images         │───▶│   OCR Engine    │───▶│   Data Format   │
│  (JPG/PNG)      │    │   + MRZ         │    │  + Probabilities │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Google Sheets  │    │      CSV        │    │ Postprocessing  │
│   Integration   │◀───│   Results       │◀───│  + Country      │
│ + Probabilities │    │ + Probabilities │    │    Rules        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🔄 Data Flow

### 1. **Image Processing**
```python
# Input: Passport images in data/Philippines/[maid_id]/
images = _list_image_files(folder)  # Find all valid image files
raw = recognize_images(images)      # Regula OCR extraction
```

### 2. **Field Extraction & Probability Mapping**
```python
# Regula returns probabilities 0-100, normalized to 0.0-1.0
uni = regula_to_universal(raw)      # Extract fields + probabilities
# Output: {"number": "P1234567A", "name": "JOHN", probabilities: {"number": 0.97, "name": 0.95}}
```

### 3. **Domain-Specific Postprocessing**
```python
uni = postprocess(uni)              # Apply smart validation
# - Date format standardization (dd/mm/YYYY)
# - Place of issue → country of issue mapping
# - Country code validation and normalization
# - Place of birth cleaning
```

### 4. **Country-Specific Rules**
```python
formatted_data = country_rules(formatted_data, country)
# Philippines: Document number validation (A/B/C endings)
# Kenya: Prefix validation (AK/BK/CK) + place matching
# India: Name field rearrangement + mother name processing
# + 17 more countries
```

### 5. **CSV Export with Probabilities**
```csv
inputs.image_id,outputs.number,outputs.name,probability.number,probability.name
47648,P7264272A,ELAINE,0.97,0.97
```

### 6. **Google Sheets Integration**
```python
ResultsAgent().upload_results(csv_file)
# Merges with existing review data
# Uploads values + probability scores
# Handles data type conversion and validation
```

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.11+
- Conda environment manager
- Regula Document Reader service running on localhost:8080
- Google Sheets API credentials

### Environment Setup
```bash
# Create conda environment
conda create -n regula python=3.11
conda activate regula

# Install dependencies
pip install -r requirements.txt

# For optional country lookup
pip install pycountry
```

### Configuration Files
```
├── credentials.json          # Google Sheets API credentials
├── token.pickle             # OAuth token cache
├── static/
│   ├── country_codes.csv     # Country name → code mapping
│   ├── city_country.csv      # City → country mapping
│   ├── birth_places.csv      # Valid birth places
│   └── consolidated_data.parquet  # Review data cache
```

## 🚦 Usage

### Basic Processing
```python
# Process all images in data/Philippines/
python main.py

# Output:
# - results/regula_Philippines_results.csv
# - results/test/[maid_id].json (debug files)
# - Google Sheets upload
```

### Advanced Usage
```python
from src.adapters.regula_client import recognize_images
from src.adapters.regula_mapper import regula_to_universal
from src.utils import postprocess

# Process specific images
images = ["path/to/passport1.jpg", "path/to/passport2.jpg"]
raw = recognize_images(images)
universal = regula_to_universal(raw)
processed = postprocess(universal)

print(f"Name: {processed['name']} (confidence: {processed['probabilities']['name']})")
```

## 📊 Output Format

### CSV Structure
```csv
# Core Data
inputs.image_id              # Maid ID
outputs.number               # Passport number
outputs.name                 # First name
outputs.surname              # Last name
outputs.birth_date           # dd/mm/YYYY format
...

# Probability Scores (0.0-1.0)
probability.number           # Confidence in passport number
probability.name             # Confidence in name extraction
probability.surname          # Confidence in surname
...
```

### Google Sheets Format
```
Maid's ID | Modified Field | Regula Value | Regula Probability | Similarity
47648     | First Name     | ELAINE       | 0.97              | true
47648     | Last Name      | SARGUIT      | 1.0               | true
```

## 🔧 Key Components

### Core Modules

1. **`regula_client.py`** - Regula API interface
   ```python
   recognize_images(image_paths) → raw_response
   ```

2. **`regula_mapper.py`** - Field extraction & probability normalization
   ```python
   regula_to_universal(raw) → {fields + probabilities}
   ```

3. **`passport_processing.py`** - Domain-specific postprocessing
   ```python
   postprocess(data) → validated_data_with_probabilities
   ```

4. **`country_rules.py`** - Country-specific validation
   ```python
   country_rules(data, country_code) → country_validated_data
   ```

5. **`results_utils.py`** - Google Sheets integration
   ```python
   ResultsAgent().upload_results(csv_path) → sheets_upload
   ```

### Configuration

```python
# main.py - Adjust these settings
IMAGE_PATH = "data/Philippines"           # Source folder
DATASET_COUNTRY = "Philippines"           # Country name
SPREADSHEET_ID = "your_sheet_id"         # Google Sheets ID
CREDENTIALS_PATH = "credentials.json"     # API credentials
```

## 🌍 Supported Countries

| Country | Code | Validation Features |
|---------|------|-------------------|
| Philippines | PHL | Document format (A/B/C), OCR correction |
| Kenya | KEN | Prefix validation (AK/BK/CK), place matching |
| Ethiopia | ETH | Prefix validation (EQ/EP), digit verification |
| India | IND | Name rearrangement, mother name processing |
| Sri Lanka | LKA | Place authority detection, number processing |
| Nepal | NPL | MOFA detection, number truncation |
| Uganda | UGA | Field clearing rules |
| Pakistan | PAK | Name rearrangement, father name parsing |
| Myanmar | MMR | Full name parsing and splitting |
| + 11 more | ... | Standard place/country assignments |

## 🔍 Probability System

### Regula Confidence Scores
- **Input**: Raw Regula probabilities (0-100)
- **Normalization**: Converted to 0.0-1.0 scale
- **Preservation**: Maintained through all processing steps
- **Enhancement**: Country rules can adjust confidence based on validation

### Confidence Interpretation
- **1.0**: Perfect extraction (MRZ validated)
- **0.9-0.99**: High confidence (clear OCR)
- **0.7-0.89**: Good confidence (minor OCR issues)
- **0.5-0.69**: Moderate confidence (validation concerns)
- **0.0-0.49**: Low confidence (needs review)

## 🚨 Error Handling

### Graceful Degradation
```python
# Missing dependencies
try:
    import pycountry
except ImportError:
    pycountry = None  # Country lookup disabled

# Invalid image processing
try:
    raw = recognize_images(images)
except Exception as e:
    skipped.append((maid_id, f"error: {e}"))
```

### Debug Output
- JSON dumps for each processed maid in `results/test/`
- Detailed error logging with maid ID tracking
- Probability tracking through each processing step

## 📈 Performance

### Optimization Features
- **Cached Consolidated Data**: Review data cached in parquet format
- **Batch Processing**: Multiple images per maid processed together
- **Efficient Merging**: Smart data type handling for sheet integration
- **Probability Preservation**: No redundant calculations

### Typical Processing Times
- **Single passport**: ~2-5 seconds
- **Batch of 100**: ~5-10 minutes
- **Google Sheets upload**: ~30 seconds per batch

## 🔒 Security & Privacy

- **Local Processing**: All OCR processing happens locally
- **Credential Management**: Google API credentials stored securely
- **Data Retention**: Debug files contain sensitive data - manage carefully
- **Access Control**: Google Sheets access controlled via service account

## 🐛 Troubleshooting

### Common Issues

1. **"ModuleNotFoundError: pycountry"**
   ```bash
   pip install pycountry
   # Or system will work without it (country lookup disabled)
   ```

2. **"KeyError: Maid's ID"**
   - Check consolidated data format
   - Verify data type compatibility (int vs string)

3. **Probabilities showing as 0.0**
   - Verify CSV has probability.* columns
   - Check data merge between CSV and review data

4. **Google Sheets upload fails**
   - Verify credentials.json exists and is valid
   - Check spreadsheet ID and permissions
   - Ensure token.pickle is not corrupted

### Debug Mode
```python
# Enable detailed logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📄 License

This project is proprietary software for internal use.

## 🤝 Contributing

1. Follow existing code patterns
2. Maintain probability tracking through all changes
3. Add country-specific rules in `country_rules.py`
4. Update this README for significant changes

---

**Note**: This system is optimized for passport processing with Regula's advanced OCR capabilities. The probability tracking and country-specific validation make it highly suitable for production maid passport verification workflows.
