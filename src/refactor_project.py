import os
from pathlib import Path
import shutil

# Base directory of your existing project
base_dir = Path("/")
src_dir = base_dir

# Target directory structure for refactoring
structure = {
    "cli": ["main.py", "classification.py"],
    "ingestion": ["data_ingestion.py", "qfx_importer.py", "pdf_extractor.py"],
    "classification": ["ml_classifier.py"],
    "budgeting": ["budget_forecast.py", "budget_cashflow.py"],
    "tax": ["tax_management.py", "tax_section_179.py"],
    "ui": ["ui.py"],
}

# Function to refactor files into the new directory structure
def refactor_structure(base_path, new_structure):
    new_base = base_path / "refactored_src"
    os.makedirs(new_base, exist_ok=True)

    for folder, files in new_structure.items():
        target_folder = new_base / folder
        os.makedirs(target_folder, exist_ok=True)
        for file in files:
            src_file = base_path / file
            if src_file.exists():
                shutil.copy(src_file, target_folder / file)

    return new_base

refactored_path = refactor_structure(src_dir, structure)
refactored_path.as_posix()

