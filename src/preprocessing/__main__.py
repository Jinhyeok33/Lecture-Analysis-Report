import os
from pathlib import Path
from dotenv import load_dotenv

from .preprocessing import DictionaryGenerator, RuleBasedPreprocessor

load_dotenv()


def main():
    repo_root = Path(__file__).resolve().parents[2]

    raw_dir = repo_root / "data" / "raw"
    preprocessed_dir = repo_root / "data" / "preprocessed"
    resource_dir = repo_root / "src" / "preprocessing" / "resources"
    metadata_path = repo_root / "data" / "metadata" / "lecture_metadata.csv"
    dict_path = resource_dir / "term_mapping_dict.json"

    preprocessed_dir.mkdir(parents=True, exist_ok=True)
    resource_dir.mkdir(parents=True, exist_ok=True)

    print("=== Preprocessing pipeline start ===")
    print("[1/2] Build or update terminology dictionary")

    generator = DictionaryGenerator(
        raw_folder_path=str(raw_dir),
        metadata_path=str(metadata_path),
    )
    generator.build_or_update_dictionary(chunk_size=200, save_path=str(dict_path))

    print("[2/2] Apply rule-based preprocessing")
    preprocessor = RuleBasedPreprocessor(dict_path=str(dict_path))
    preprocessor.process_files(input_folder=str(raw_dir), output_folder=str(preprocessed_dir))

    print("=== Preprocessing pipeline complete ===")


if __name__ == "__main__":
    main()
