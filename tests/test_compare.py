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
import pytest

from .utils import get_files, make_config
from helpers.fileset_comparator import FilesetComparator
from files.generic import UnpackedFile
from files.symlink import SymlinkFile


@pytest.fixture
def path1():
    return "tests/data/test1"


@pytest.fixture
def path2():
    return "tests/data/test2"


@pytest.fixture
def config():
    config = make_config()
    config.update("extract", False)
    return config


def make_comparator(config, path1, path2):
    files1, files2 = get_files(config, path1, path2)
    return FilesetComparator(files1, files2, config)


def test_compare(config, path1, path2):
    comparator = make_comparator(config, path1, path2)
    pairs = comparator.get_files_to_compare()
    pairs = list(pairs)

    assert len(pairs) == 2
    assert len(comparator.added_files) == 0
    assert len(comparator.removed_files) == 0


def test_compare_specialize(config, path1, path2):
    config.update("exclude", ["*.txt"])
    comparator = make_comparator(config, path1, path2)
    pairs = comparator.get_files_to_compare()

    for pair in pairs:
        assert isinstance(pair[0], SymlinkFile)
        assert isinstance(pair[1], SymlinkFile)


def test_compare_no_specialize(config, path1, path2):
    config.update("specialize", False)
    comparator = make_comparator(config, path1, path2)
    pairs = comparator.get_files_to_compare()

    for pair in pairs:
        assert pair[0].__class__ == UnpackedFile
        assert pair[1].__class__ == UnpackedFile


def test_compare_no_matching(config, path1, path2):
    comparator = make_comparator(config, path1, path2)
    config.update("fuzzy_threshold", 0)

    pairs = comparator.get_files_to_compare()
    pairs = list(pairs)

    assert len(pairs) == 1
    assert len(comparator.added_files) == 1
    assert len(comparator.removed_files) == 1
