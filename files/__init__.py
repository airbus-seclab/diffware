from . import generic, elf


# Order matters: file type recognition is called in order
FILE_TYPES = [
    elf.ElfFile,
    generic.UnpackedFile
]
