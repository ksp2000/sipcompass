"""Data persistence module for saving and loading processed data."""

import os
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd
import yaml


PROCESSED_DIR = "data/processed"


def ensure_processed_dir():
    """Create processed data directory if it doesn't exist."""
    Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)


def save_processed_data(df: pd.DataFrame, metadata: dict, base_name: str) -> tuple[str, str]:
    """
    Save processed DataFrame and metadata to Parquet and YAML files.
    
    Args:
        df: DataFrame with all indicators and signals computed
        metadata: Dictionary with source info, params, date range, etc.
        base_name: Base filename without extension (e.g., 'NIFTYBEES_20200101_20260109')
    
    Returns:
        Tuple of (parquet_path, metadata_path)
    """
    ensure_processed_dir()
    
    parquet_path = os.path.join(PROCESSED_DIR, f"{base_name}_processed.parquet")
    metadata_path = os.path.join(PROCESSED_DIR, f"{base_name}_metadata.yaml")
    
    # Save DataFrame to Parquet
    df.to_parquet(parquet_path, index=False, engine='pyarrow')
    
    # Add generation timestamp to metadata
    metadata['generated_at'] = datetime.now().isoformat()
    metadata['rows'] = len(df)
    
    # Save metadata to YAML
    with open(metadata_path, 'w') as f:
        yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)
    
    return parquet_path, metadata_path


def load_processed_data(parquet_path: str) -> tuple[pd.DataFrame, dict]:
    """
    Load processed DataFrame and its metadata.
    
    Args:
        parquet_path: Path to the .parquet file
    
    Returns:
        Tuple of (DataFrame, metadata_dict)
    
    Raises:
        FileNotFoundError: If parquet file or metadata not found
        ValueError: If required columns are missing
    """
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"Processed data file not found: {parquet_path}")
    
    # Load DataFrame
    df = pd.read_parquet(parquet_path, engine='pyarrow')
    
    # Load metadata
    metadata_path = parquet_path.replace('_processed.parquet', '_metadata.yaml')
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
    
    with open(metadata_path, 'r') as f:
        metadata = yaml.safe_load(f)
    
    # Validate required columns
    required_columns = [
        'Date', 'Close', 'buy_signal', 'intensity_level', 'investment_amount'
    ]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Processed data missing required columns: {missing}")
    
    return df, metadata


def list_processed_files() -> list[dict]:
    """
    List all available processed data files with their metadata.
    
    Returns:
        List of dicts with keys: filename, parquet_path, metadata_path, 
        date_range, rows, generated_at, source_type, identifier
    """
    ensure_processed_dir()
    
    parquet_files = glob.glob(os.path.join(PROCESSED_DIR, "*_processed.parquet"))
    results = []
    
    for parquet_path in sorted(parquet_files):
        metadata_path = parquet_path.replace('_processed.parquet', '_metadata.yaml')
        
        # Extract base filename
        filename = os.path.basename(parquet_path)
        
        # Try to load metadata
        metadata = {}
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = yaml.safe_load(f)
            except Exception:
                pass  # Skip if metadata is corrupted
        
        # Extract info
        date_range = metadata.get('date_range', {})
        data_source = metadata.get('data_source', {})
        
        results.append({
            'filename': filename,
            'parquet_path': parquet_path,
            'metadata_path': metadata_path,
            'date_range': f"{date_range.get('start', 'N/A')} → {date_range.get('end', 'N/A')}",
            'rows': metadata.get('rows', 0),
            'generated_at': metadata.get('generated_at', 'Unknown'),
            'source_type': data_source.get('type', 'Unknown'),
            'identifier': data_source.get('ticker') or data_source.get('scheme_code', 'Unknown'),
        })
    
    return results


def generate_base_name(identifier: str, start_date: str, end_date: str) -> str:
    """
    Generate base filename for processed data.
    
    Args:
        identifier: Ticker symbol or scheme code
        start_date: Start date (YYYY-MM-DD or YYYYMMDD)
        end_date: End date (YYYY-MM-DD or YYYYMMDD)
    
    Returns:
        Base filename without extension (e.g., 'NIFTYBEES_20200101_20260109')
    """
    def fmt_date(date_str: str) -> str:
        try:
            return datetime.fromisoformat(date_str[:10]).strftime('%Y%m%d')
        except ValueError:
            return date_str.replace('-', '')
    
    start_label = fmt_date(start_date) if start_date else 'start'
    end_label = fmt_date(end_date) if end_date else 'latest'
    
    return f"{identifier}_{start_label}_{end_label}"
