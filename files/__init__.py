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
# The `files` folder contains classes used to represent specialized files,
# as well as classes needed to analyze their contents
from . import elf, symlink


# Order matters: file type recognition is called in order
# No need to add generic.UnpackedFile as all files are instances of this class
# by default
FILE_TYPES = [
    elf.ElfFile,
    symlink.SymlinkFile
]
