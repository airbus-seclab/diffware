import os
import tlsh
import pathlib
import subprocess
from functools import wraps
from configparser import NoOptionError, NoSectionError

from fact_helper_file import get_file_type_from_path


def get_file_type(path):
    path = pathlib.Path(path)

    # Make sure symlinks aren't followed
    if path.is_symlink():
        return {"mime": "inode/symlink", "full": ""}

    # get_file_type_from_path would raise IsADirectoryError
    if path.is_dir():
        return {"mime": "directory", "full": ""}

    return get_file_type_from_path(path)


def compute_distance(file1, file2):
    """
    Use tlsh to compute the distance between 2 files
    If it fails, revert to counting the number of different bytes
    """
    try:
        return tlsh.diff(file1.fuzzy_hash, file2.fuzzy_hash)
    except (TypeError, ValueError):
        # File is too small or doesn't have enough randomness
        pass

    # Compute the proportion of bytes changed
    path1 = str(file1.path)
    path2 = str(file2.path)
    file_size = max(os.path.getsize(path1), os.path.getsize(path2))

    try:
        diff_bytes = subprocess.check_output(["cmp", "-l", path1, path2], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        # When files are different, cmp has an exit code of 1
        diff_bytes = e.output

    # Diff is size of output, multiplied by a constant to be the same order of
    # magnitude as TLSH's distance, and set at a min value of 1
    diff = int(10 * len(diff_bytes) / max(1, file_size))
    return max(diff, 1)


def read_list_from_config(config_file, section, key, fallback=None):
    """
    Inspired by https://github.com/fkie-cad/fact_extractor/blob/master/fact_extractor/helperFunctions/config.py
    """
    fallback = fallback or []

    try:
        value = config_file.get(section, key)
    except (NoOptionError, NoSectionError):
        value = None

    if not value:
        return fallback

    return [item.strip() for item in value.split(",") if item]
