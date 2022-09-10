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
from helpers.config import Config
from helpers.logger import Logger
from helpers.runner import Runner


def get_files(config, path1, path2):
    runner = Runner(config)
    files1, files2, _, _ = runner.get_extracted_files(path1, path2)
    return list(files1), list(files2)


def make_config():
    config = Config()
    Logger.setup_logging(progress=False, output_file="/dev/null")
    return config
