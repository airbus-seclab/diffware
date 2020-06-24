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
