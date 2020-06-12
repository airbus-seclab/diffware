import os
import re
import tlsh
import subprocess
import collections

from .generic import UnpackedFile
from utils import cached_property
from profiler import Profiler
from logger import Logger
from file_comparator import FileComparator

from fact_helper_file import get_file_type_from_path


class ElfSection:
    def __init__(self, path, section_name):
        self.name = section_name
        self.path = path

        path_dir = re.escape(os.path.dirname(self.path).encode("utf-8"))
        path = re.escape(self.path.encode("utf-8"))

        # Match the directory containing the file
        self._dir_re = re.compile(
            rb"%s\b" % path_dir
        )
        # Match the full path to the file
        self._path_re = re.compile(rb"%s\b" % path)
        # Match hex offset
        self._offset_re = re.compile(rb"offset 0x[0-9a-f]+")

    def _cmd_options(self):
        return ["--decompress", "--hex-dump"]

    def _cmd(self, file):
        return ["readelf", *self._cmd_options(),self.name, file]

    @Profiler.profilable
    def analyze(self, file, stdout):
        self._process = subprocess.run(
            self._cmd(file),
            shell=False,
            close_fds=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

    def _filter(self, line):
        # The full path can appear in the output, we need to remove it
        line = self._path_re.sub(b"/file", line)
        line = self._dir_re.sub(b"/", line)
        # Offsets can change if headers are modified, but don't reflect
        # real modifications in behavior
        return self._offset_re.sub(b"offset 0x", line)

    @Profiler.profilable
    def read(self):
        for line in self._process.stdout.splitlines(True):
            yield self._filter(line)


class ElfCodeSection(ElfSection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Match the leading hex value (offset of the instruction)
        self._line_regex = re.compile(rb'^\s*[0-9a-f]+:\s*')
        # Match addresses that have been resolved to a symbol
        # First, parse lines that look like:
        # "​callq 4f60 <call_gmon_start>"
        self._resolved_regex = re.compile(rb'\b([0-9a-f]+)(?=\s+\<\S+\>)')
        # Then, parse lines that look like:
        # "lea  0x111cb4 (%rip),%rsi     # 12a012 <_fini+0xc4>"
        self._pointer_regex = re.compile(rb'\b(0x[0-9a-f]+)\b(?=.*\<\S+\>)')

    def _cmd_options(self):
        return ["--line-numbers", "--disassemble", "--demangle", "--reloc", "--no-show-raw-insn"]

    def _cmd(self, file):
        return ["objdump", *self._cmd_options(), "--section", self.name, file]

    def _filter(self, line):
        line = super()._filter(line)
        line = self._line_regex.sub(b"", line)
        line = self._resolved_regex.sub(b"", line)
        return self._pointer_regex.sub(b"0x ", line)


class ElfStringSection(ElfSection):
    def _cmd_options(self):
        return ["--decompress", "--string-dump"]


class ElfFile(UnpackedFile):
    recognize_regex = re.compile(r"^ELF\s")

    # Ignore sections that are not included in this list
    # See https://refspecs.linuxfoundation.org/LSB_2.1.0/LSB-Core-generic/LSB-Core-generic/specialsections.html
    KEEP_SECTIONS = [
        ".rodata",
        ".rodata1",
        ".data",
        ".data1",
        ".text",
        ".preinit_array",
        ".init",
        ".init_array",
        ".fini",
        ".fini_array",
        ".ctors",
        ".dtors",
        # Special names for sections with errors
        "<no-strings>",
        "<corrupt>"
    ]

    SECTION_FLAG_MAPPING = {
        "X": ElfCodeSection,
        "S": ElfStringSection,
        "_": ElfSection,
    }

    @cached_property
    def _comparable_path(self):
        # Use readelf and objdump to extract the useful info and write it to
        # a temporary file
        tmp_file_path = FileComparator.tmp_file_path()
        absolute_path = self.path.absolute().as_posix()

        self._sections = None
        self._load_sections(absolute_path)

        # If there were no sections, default to comparing the whole file
        if not self._sections:
            return self.path

        with open(tmp_file_path, "wb") as tmp:
            for section in self._sections.values():
                section.analyze(absolute_path, tmp)
                for line in section.read():
                    tmp.write(line)

        return tmp_file_path

    def _should_skip_section(self, name, type):
        return name not in self.KEEP_SECTIONS

    @Profiler.profilable
    def _load_sections(self, file):
        """
        Inspired by diffoscope/comparator/elf.py ElfContainer
        """
        cmd = [
            "readelf",
            "--wide",
            "--section-headers",
            file,
        ]
        output = subprocess.check_output(
            cmd, shell=False, stderr=subprocess.DEVNULL
        )

        try:
            output = output.decode("utf-8").split("\n")
            if output[1].startswith("File:"):
                output = output[2:]
            output = output[5:]

            # Entries of readelf --section-headers have the following columns:
            # [Nr]  Name  Type  Address  Off  Size  ES  Flg  Lk  Inf  Al
            self._sections = collections.OrderedDict()

            for line in output:
                if line.startswith("Key to Flags"):
                    break

                # Strip number column because there may be spaces in the brakets
                line = line.split("]", 1)[1].split()
                name, type, flags = line[0], line[1], line[6] + "_"

                if self._should_skip_section(name, type):
                    continue

                # Use first match, with last option being "_" as fallback
                elf_class = [
                    self.SECTION_FLAG_MAPPING[x]
                    for x in flags
                    if x in self.SECTION_FLAG_MAPPING
                ][0]

                self._sections[name] = elf_class(file, name)
        except Exception as e:
            Logger.error("error in _load_sections", e)
            pass
