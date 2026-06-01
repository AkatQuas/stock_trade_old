from pathlib import Path


def get_script_parent_folder_path():
    script_path = Path(__file__).resolve()

    return script_path.parent.parent


def get_file_in_pack(*path_segments: str | Path) -> Path:
    combined_path = get_script_parent_folder_path()
    for segment in path_segments:
        combined_path = combined_path / segment

    return combined_path.resolve()


if __name__ == "__main__":
    print(get_file_in_pack("../../stocklist.csv"))
