"""
Copyright (C) 2020 Jean-Romain Garnier <github@jean-romain.com>

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
import sys
import shutil
import logging
import pathlib
import fnmatch
from copy import deepcopy
from functools import lru_cache

try:
    # Try to import fact_extractor if possible, otherwise
    # disable unpacking
    current_dir = pathlib.Path(__file__).parent.absolute()
    fact_dir = current_dir.parent.parent / "fact_extractor" / "fact_extractor"
    sys.path.append(str(fact_dir))

    from unpacker.unpack import Unpacker
    FACT_FOUND = True
except ModuleNotFoundError:
    FACT_FOUND = False

import files
from .logger import Logger
from .file_comparator import FileComparator
from .fileset_comparator import FilesetComparator
from .utils import get_file_type, read_list_from_config


def _copy_if_necessary(file_path, source_folder, destination_folder):
    """
    Copy the given file to the output folder, if it's not already there
    """
    try:
        # Get the relative path for this file from the source folder
        relative_path = file_path.relative_to(source_folder)

        # Keep the same relative path, but from the destination folder
        target_path = pathlib.Path(destination_folder, relative_path)
        os.makedirs(target_path.parent, exist_ok=True)

        return shutil.copy(file_path, target_path, follow_symlinks=False)
    except ValueError:
        # relative_to will fail for files which are not located in the
        # source_folder (so they must be in the destination_folder)
        return file_path
    except shutil.SameFileError:
        # Copy may fail if the file is already in the right location
        return file_path
    except FileExistsError as e:
        # When handling symlinks, attempting to override an existing link
        # with another will fail
        Logger.warn(e)
        return file_path


def _delete_if_necessary(file_path, config):
    """
    Delete the given file, if user asked to and if it's not in the source_folder
    """
    if not config.clean_extracted:
        return

    if pathlib.Path(config.source_folder) in file_path.parents:
        return

    os.remove(file_path)


def output_change(edit, config):
    path1, path2, distance = edit

    if config.compute_distance:
        Logger.output("\nFile1: {}\nFile2: {}\nDistance: {}".format(
            path1,
            path2,
            distance
        ))
    else:
        Logger.output("\nFile1: {}\nFile2: {}".format(
            path1,
            path2
        ))


class Runner:
    """
    Main class used to compared two files or directories
    """

    def __init__(self, config):
        self.config = config
        self.excluded = read_list_from_config(config, "unpack", "exclude") or []
        self.excluded_mimes = config.exclude_mime

        if config.extract and not FACT_FOUND:
            raise ModuleNotFoundError(
                "fact_extractor not found on your system, please use the --no-extract option or see the install instructions"
            )

    def list_files(self, file_path):
        """
        List all the files at the given path, excluding those that should be
        excluded
        """

        if self.is_excluded(file_path):
            return

        if file_path.is_dir():
            data_folder = file_path
            for path in self._walk(file_path):
                yield files.generic.UnpackedFile(path, self.config, data_folder)
        else:
            data_folder = file_path.parent
            yield files.generic.UnpackedFile(file_path, self.config, data_folder)

    def get_extracted_files(self, file_path1, file_path2):
        """
        Recursively extract the content of both file paths and return a list of
        files contained in each one
        """
        file_path1 = pathlib.Path(file_path1).resolve()
        file_path2 = pathlib.Path(file_path2).resolve()

        config1 = deepcopy(self.config)
        config1.update("data_folder", self.config.get("unpack", "data_folder_1"))

        config2 = deepcopy(self.config)
        config2.update("data_folder", self.config.get("unpack", "data_folder_2"))

        # Create output "report" folder or fact extractor will crash
        report_path = os.path.join(config1.get("unpack", "data_folder"), "reports")
        os.makedirs(report_path, exist_ok=True)

        report_path = os.path.join(config2.get("unpack", "data_folder"), "reports")
        os.makedirs(report_path, exist_ok=True)

        if self.config.extract:
            unpacker1 = Unpacker(config=config1)
            unpacker2 = Unpacker(config=config2)

            files1 = self.extract(file_path1, unpacker1, config1)
            files2 = self.extract(file_path2, unpacker2, config2)

            data_folder_1 = "/tmp/extractor1"
            data_folder_2 = "/tmp/extractor2"
        else:
            files1 = self.list_files(file_path1)
            files2 = self.list_files(file_path2)

            data_folder_1 = file_path1 if file_path1.is_dir() else file_path1.parent
            data_folder_2 = file_path2 if file_path2.is_dir() else file_path2.parent

        return files1, files2, data_folder_1, data_folder_2

    def extract(self, file_path, unpacker, config):
        """
        Recursively extract the content of a file or folder
        """
        data_folder = config.get("unpack", "data_folder")
        max_depth = config.max_depth

        # Resolve symlinks and get absolute paths once so we don't run into
        # issues later on by attempting to resolve broken symlinks that were
        # extracted
        data_folder = pathlib.Path(data_folder, "files").resolve()

        if file_path.is_dir():
            # Walk through folders and extract only the files they contain
            config.source_folder = file_path
            config.data_folder = data_folder
            for path in self._walk(file_path):
                yield from self._extract(path, unpacker, config)
        else:
            # Regular files can just be extracted
            config.source_folder = file_path.parent
            config.data_folder = data_folder
            yield from self._extract(file_path, unpacker, config)


    ### Helper methods

    @lru_cache(maxsize=128, typed=False)
    def _is_mime_excluded(self, mime_type):
        for pattern in self.excluded_mimes:
            if fnmatch.fnmatchcase(mime_type, pattern):
                return True

    def is_excluded(self, path):
        for pattern in self.excluded:
            if fnmatch.fnmatchcase(str(path), pattern):
                Logger.debug("Ignoring file {}".format(path))
                return True

        # Don't find mime type if there is no rule to exclude it
        if self.excluded_mimes:
            mime_type = get_file_type(path)["mime"]
            if self._is_mime_excluded(mime_type):
                Logger.debug("Ignoring file {} with mime-type {}".format(path, mime_type))
                return True

        return False


    ### Private methods

    def _extract(self, file_path, unpacker, config, depth=0):
        """
        Assume file_path is not a directory, and either recursively extract its
        content, or return the plain file if there is nothing to extract
        """
        # Ignore unwanted files
        if self.is_excluded(file_path):
            return

        # Make sure recursion max depth isn't exceeded
        should_skip = False
        if config.max_depth >= 0 and depth > config.max_depth:
            Logger.warn("Max recursion depth reached, skipping {}".format(file_path))
            should_skip = True
        else:
            Logger.progress("Unpacking {}...".format(file_path))

        # Symlinks shouln't be followed
        if file_path.is_symlink():
            should_skip = True

        # Update the "_file_folder" value from the unpacker so fact_extractor
        # doesn't extract in the root output folder, making everything
        # messy and breaking the original hierachy
        try:
            relative_path = file_path.relative_to(config.data_folder)
            extract_folder = pathlib.Path(config.data_folder, str(relative_path) + "_extracted")
        except ValueError:
            # This file is still in the source_folder, so no need to bother
            extract_folder = config.data_folder

        unpacker._file_folder = extract_folder

        # Attempt to extract file, if necessary
        extracted_count = 0
        if not should_skip:
            for path in unpacker.unpack(file_path):
                # unpack already does the walk for us, so we can just call _extract
                # again
                extracted_count += 1
                yield from self._extract(path, unpacker, config, depth=depth + 1)

        if extracted_count == 0:
            # If no files were extracted, at least return this file
            # _copy_if_necessary takes care of handling symlinks
            path = _copy_if_necessary(file_path, config.source_folder, config.data_folder)
            yield files.generic.UnpackedFile(path, config, config.data_folder)
        else:
            # Since the content was extracted, we can delete this file
            _delete_if_necessary(file_path, config)

    def _walk(self, file_path):
        """
        Generator to walk the files included in a directory
        """
        for root, _, files in os.walk(file_path):
            for name in files:
                file = pathlib.Path(root, name)

                Logger.progress("Walking {}...".format(file))
                if not self.is_excluded(file):
                    yield file
