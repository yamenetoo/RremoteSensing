import pickle
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from typing import Union
from .core import process_spectrum, create_material_interp_function

def build_material_library(
    csv_dir: Union[str, Path],
    output_path: Union[str, Path],
    base_path: Union[str, Path, None] = None,
    plot: bool = False,
    column_indices: list = [0, 2, 4]
) -> dict:
    """
    Batch process USGS Splib07 CSV files and save interpolation functions to a pickle file.
    """
    csv_dir = Path(csv_dir)
    if not csv_dir.is_dir():
        raise FileNotFoundError(f"CSV directory not found: {csv_dir}")

    csv_files = sorted(csv_dir.glob("*.csv"))
    library = {"name": [], "fn": []}

    for csv_file in csv_files:
        print(f"📖 Processing {csv_file.name}...")
        df = pd.read_csv(csv_file)
        df = df.iloc[:, column_indices]

        for i in tqdm(range(df.shape[0]), desc=f"  {csv_file.name}", unit="material", leave=False):
            try:
                name, spectrum = process_spectrum(df.iloc[i], plot=plot, base_path=base_path)
                if spectrum.shape[0] > 0:
                    fn = create_material_interp_function(spectrum)
                    library["name"].append(name)
                    library["fn"].append(fn)
            except Exception as e:
                print(f"⚠️ Error at row {i} in {csv_file.name}: {e}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        pickle.dump(library, f)

    print(f"✅ Saved {len(library['name'])} materials to {output_path}")
    return library


def load_material_library(path: Union[str, Path]) -> dict:
    """Load a previously saved material library from a pickle file."""
    with open(path, 'rb') as f:
        return pickle.load(f)
