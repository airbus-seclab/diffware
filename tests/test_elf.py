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
from helpers.file_comparator import FileComparator
from helpers.fileset_comparator import FilesetComparator
from files.elf import ElfFile


@pytest.fixture
def path1():
    return "tests/data/test1.o"


@pytest.fixture
def path2():
    return "tests/data/test2.o"


@pytest.fixture
def config():
    config = make_config()
    config.update("extract", False)
    return config


def make_comparator(config, path1, path2):
    files1, files2 = get_files(config, path1, path2)
    return FilesetComparator(files1, files2, config)


def test_specialize(config, path1, path2):
    comparator = make_comparator(config, path1, path2)
    pairs = comparator.get_files_to_compare()
    file1, file2 = next(pairs)

    assert isinstance(file1, ElfFile)
    assert isinstance(file2, ElfFile)


def test_equal(config, path1):
    comparator = make_comparator(config, path1, path1)
    pairs = comparator.get_files_to_compare()
    file1, file2 = next(pairs)

    assert FileComparator.are_equal(file1, file2)


def test_different(config, path1, path2):
    comparator = make_comparator(config, path1, path2)
    pairs = comparator.get_files_to_compare()
    file1, file2 = next(pairs)

    assert not FileComparator.are_equal(file1, file2)
