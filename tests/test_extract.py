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
import pytest

from .utils import get_files, make_config
from helpers.config import Config


@pytest.fixture
def path1():
    return "tests/data/test1.7z"


@pytest.fixture
def path2():
    return "tests/data/test2.7z"


@pytest.fixture
def config():
    return make_config()


def test_extraction(config, path1, path2):
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 2
    assert len(files2) == 2


def test_extraction_exclude(config, path1, path2):
    config.update("exclude", ["*/broken*"])
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 1
    assert len(files2) == 1


def test_extraction_exclude_mime(config, path1, path2):
    config.update("exclude", ["*/broken*"])
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 1
    assert len(files2) == 1
