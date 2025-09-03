import os
import json
import pickle
import traceback
from collections import Counter

import gspread
import pandas as pd
from fuzzywuzzy import process
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ======== CONFIG / CONSTANTS ========
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

pd.options.mode.chained_assignment = None

# Country code mapping (e.g., "Kenya" -> "KEN")
country_codes = pd.read_csv("static/country_codes.csv")
mapper = dict(zip(country_codes["country"], country_codes["code"]))


class ResultsAgent:
    def __init__(
        self,
        spreadsheet_id: str = "1ljIem8te0tTKrN8N9jOOnPIRh2zMvv2WB_3FBa4ycgA",
        country: str = "XXX",
        credentials_path: str = "credentials.json",
        excel_paths: list[str] = [
            "./static/OCR Extracted Data and User Modifications (feb 1- march 31) .xlsx",
            "./static/OCR Extracted Data and User Modifications- April 1 till 28.xlsx",
            "./static/OCR Extracted Data and User Modifications (1-9-2024 till 14-5-2025).xlsx",
            "./static/OCR Extracted Data and User Modifications - all 2024.xlsx",
        ],
        consolidated_file_path: str = "./static/consolidated_data.parquet",
        sheet_column_prefix: str = "Gemini",  # keep old headers by default
    ):
        self.country = country
        self.spreadsheet_id = spreadsheet_id
        self.credentials_path = credentials_path
        self.excel_paths = excel_paths
        self.consolidated_file_path = consolidated_file_path

        self.all_df = self._load_consolidated_data()

    # ---------- Load / cache consolidated Excel data ----------

    def _load_consolidated_data(self) -> pd.DataFrame:
        if os.path.exists(self.consolidated_file_path):
            consolidated_mtime = os.path.getmtime(self.consolidated_file_path)
            for excel_path in self.excel_paths:
                if os.path.exists(excel_path) and os.path.getmtime(excel_path) > consolidated_mtime:
                    break
            else:
                print(f"Loading consolidated data from {self.consolidated_file_path}...")
                df = pd.read_parquet(self.consolidated_file_path)
                print(f"Loaded {len(df)} records from consolidated file.")
                return df

        print("Creating consolidated data file...")
        return self._create_consolidated_data()

    def _create_consolidated_data(self) -> pd.DataFrame:
        all_df = pd.DataFrame()

        for excel_path in self.excel_paths:
            if not os.path.exists(excel_path):
                print(f"Warning: File {excel_path} does not exist, skipping...")
                continue

            print(f"Loading {excel_path}...")
            try:
                excel_df = pd.read_excel(excel_path, sheet_name="Data")
            except Exception:
                try:
                    excel_df = pd.read_excel(excel_path, sheet_name="Sheet 1")
                except Exception as e:
                    print(f"Error loading {excel_path}: {e}")
                    continue

            all_df = pd.concat([all_df, excel_df], ignore_index=True)

        # forward fill, dedupe
        all_df.ffill(inplace=True)
        if {"Maid’s ID", "Modified Field"}.issubset(all_df.columns):
            all_df.drop_duplicates(subset=["Maid’s ID", "Modified Field"], inplace=True)

        # Save parquet cache
        os.makedirs(os.path.dirname(self.consolidated_file_path), exist_ok=True)
        all_df.to_parquet(self.consolidated_file_path, index=False)
        print(f"Saved consolidated data to {self.consolidated_file_path} with {len(all_df)} records.")
        return all_df

    def refresh_consolidated_data(self):
        if os.path.exists(self.consolidated_file_path):
            os.remove(self.consolidated_file_path)
        self.all_df = self._create_consolidated_data()

    # ---------- Transform helpers ----------

    def edit_agent_value(self, value, field):
        """
        Normalize 'Agent Value' from the review Excel to compare properly.
        Matches your prior behavior.
        """
        value = str(value).strip().upper()

        # Date -> dd/mm/YYYY
        try:
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.notna(parsed) and value and "-" in value:
                return parsed.strftime("%d/%m/%Y")
        except Exception:
            pass

        # NATIONALITY -> 3-letter code
        if str(field).strip().upper() == "NATIONALITY":
            normalized_value = process.extractOne(value, mapper.keys())
            return mapper.get(normalized_value[0], "XXX")

        # India name special-cases
        if self.country != "India" and str(field).strip().upper() in {"MOTHER NAME", "FATHER NAME"}:
            return ""
        if self.country == "India" and str(field).strip().upper() == "MOTHER NAME":
            return value.split()[0] if value else ""
        if self.country == "India" and str(field).strip().upper() == "FATHER NAME":
            return value

        # Gender -> single letter
        if str(field).strip().upper() == "GENDER":
            return value[:1] if value else ""

        return value

    # ---------- Sheet upload ----------

    def upload_results(self, csv_file_path: str):
        token_file = "token.pickle"

        # OAuth creds
        creds = None
        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and getattr(creds, "refresh_token", None):
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        gc = gspread.authorize(creds)

        # Read Regula results
        df = pd.read_csv(csv_file_path)

        # Merge with the consolidated Excel review data
        merged_df = pd.merge(
            df,
            self.all_df,
            left_on="inputs.image_id",
            right_on="Maid’s ID",
            how="left",
        )

        # Mapping from review column names -> our outputs.* columns
        google_sheet_columns = {
            "Birth Place": "outputs.place of birth",
            "Birthdate": "outputs.birth date",
            "Country of Issue": "outputs.country of issue",
            "First Name": "outputs.name",
            "Gender": "outputs.gender",
            "Last Name": "outputs.surname",
            "Middle Name": "outputs.middle name",
            "Mother Name": "outputs.mother name",
            "Nationality": "outputs.country",
            "Passport Expiry Date": "outputs.expiry date",
            "Passport Issue Date": "outputs.issue date",
            "Passport Place(EN)": "outputs.place of issue",
            "Passport ID": "outputs.number",
        }

        value_col = f"Regula Value"       
        certainty_col = f"Regula Certainty" 

        def _get_model_value(series):
            maid_id = series.get("Maid’s ID")
            field = series.get("Modified Field")
            mapped_field = google_sheet_columns.get(field)
            if not mapped_field:
                return ""

            row = df[df["inputs.image_id"] == maid_id]
            if row.empty:
                return ""

            row = row.iloc[0]
            val = row.get(mapped_field, "")

            # Fallback for Passport ID
            if (not val or (isinstance(val, float) and pd.isna(val))) and field == "Passport ID":
                val = row.get("outputs.original number", "")

            # Clean sentinel strings
            if isinstance(val, str) and val.strip().lower() in {"nan", "none", "null", "n/a", "na"}:
                return ""
            return "" if pd.isna(val) else str(val)

        def _get_model_certainty(series):
            """Optional certainty from a 'certainty' JSON column in df; else False."""
            maid_id = series.get("Maid’s ID")
            field = series.get("Modified Field")
            mapped_field = google_sheet_columns.get(field)
            if not mapped_field:
                return False

            row = df[df["inputs.image_id"] == maid_id]
            if row.empty:
                return False

            row = row.iloc[0]
            certainty_blob = row.get("certainty", "{}")
            try:
                if isinstance(certainty_blob, str):
                    cdict = json.loads(certainty_blob)
                elif isinstance(certainty_blob, dict):
                    cdict = certainty_blob
                else:
                    return False
                field_key = mapped_field.split(".", 1)[1]  # e.g., 'number'
                val = cdict.get(field_key)
                return bool(val)
            except Exception:
                return False

        # Keep only the columns we need from the review data
        base_cols = ["Maid’s ID", "Modified Field", "Agent Value", "OCR Value", "Maid’s Nationality"]
        present_base_cols = [c for c in base_cols if c in merged_df.columns]
        filtered_df = merged_df[present_base_cols].copy()

        # Compute model outputs per row of the review data
        filtered_df[value_col] = filtered_df.apply(_get_model_value, axis=1)
        filtered_df[certainty_col] = filtered_df.apply(_get_model_certainty, axis=1)
        filtered_df["Edited Agent Value"] = filtered_df.apply(
            lambda row: self.edit_agent_value(row.get("Agent Value", ""), row.get("Modified Field", "")),
            axis=1,
        )
        filtered_df["Similarity"] = filtered_df[value_col] == filtered_df["Edited Agent Value"]

        # Arrange columns for upload
        out_cols = [
            "Maid’s ID",
            "Modified Field",
            "Edited Agent Value",
            value_col,
            "Similarity",
            certainty_col,
            "Agent Value",
            "OCR Value",
            "Maid’s Nationality",
        ]
        filtered_df = filtered_df[[c for c in out_cols if c in filtered_df.columns]]

        # Clean & types
        filtered_df.dropna(subset=["Maid’s ID"], inplace=True)
        try:
            filtered_df["Maid’s ID"] = filtered_df["Maid’s ID"].astype(int)
        except Exception:
            # If you have alphanumeric IDs, keep them as strings
            filtered_df["Maid’s ID"] = filtered_df["Maid’s ID"].astype(str)


        headers = filtered_df.columns.tolist()
        data = filtered_df.values.tolist()
        worksheet = gc.open_by_key(self.spreadsheet_id).sheet1
        worksheet.clear()
        data_to_upload = [headers] + [[str(item) for item in row] for row in data]
        worksheet.update("A1", data_to_upload)
        worksheet.freeze(rows=1)
