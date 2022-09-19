"""
Copyright (C) 2020 Airbus

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import os
import tlsh
import signal
import pathlib
import subprocess
from configparser import NoOptionError, NoSectionError

try:
    from fact_helper_file import get_file_type_from_path
    FACT_FOUND = True
except ImportError:
    # Fallback to python-magic
    FACT_FOUND = False
    from magic import from_file as _magic_from_file

from .logger import Logger


def get_file_type(path):
    path = pathlib.Path(path)

    # Make sure symlinks aren't followed
    if path.is_symlink():
        return {"mime": "inode/symlink", "full": "symbolic link"}

    # get_file_type_from_path would raise IsADirectoryError
    if path.is_dir():
        return {"mime": "directory", "full": "directory"}

    # Attempting to open this would stay stuck forever
    if path.is_fifo():
        return {"mime": "inode/fifo", "full": "fifo"}

    # Don't attempt to open sockets
    if path.is_socket():
        return {"mime": "inode/socket", "full": "socket"}

    if FACT_FOUND:
        return get_file_type_from_path(path)
    else:
        return {
            "mime": _magic_from_file(path, mime=True),
            "full": _magic_from_file(path, mime=False),
        }


def get_file_size(path, default=0):
    """
    Return the size of the file at the given path
    default will be returned if FileNotFoundError is raised
    """
    try:
        return os.stat(path).st_size
    except FileNotFoundError as e:
        # Broken symlkink?
        return default


def read_timeout(file_handle, bytes=1024, timeout=0):
    """
    Read the content of a file, and timeout if nothing happens. This may
    be useful when reading from a file that turns out to be a device, socket
    or fifo node
    A value of "0" for the timeout disables it
    """
    def handler(signum, frame):
        Logger.warn("Timed out while reading contents of {}".format(file.name))
        raise TimeoutError()

    # Setup timeout so handler is called if function takes more than
    # timeout seconds
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)

    # Attempt to read, and then disable the timeout
    data = file_handle.read(bytes)
    signal.alarm(0)

    return data


def compute_fuzzy_hash(file, path):
    """
    Compute the fuzzy hash of the given file
    cf diffoscope/comparators/utils/file.py
    """
    # tlsh is not meaningful with files smaller than 512 bytes
    if get_file_size(path) >= 512:
        h = tlsh.Tlsh()
        for buf in file._read(path):
            h.update(buf)
        h.final()

        try:
            return h.hexdigest()
        except ValueError:
            # File must contain a certain amount of randomness.
            return None

    return None


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
    file_size = max(get_file_size(path1), get_file_size(path2))

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
