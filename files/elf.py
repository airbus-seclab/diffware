import os
import re
import tlsh
import itertools
import subprocess
import collections
from functools import cached_property

from .generic import UnpackedFile
from .analyzer import Analyzer, Command, Regex

from helpers.logger import Logger
from helpers.profiler import Profiler
from helpers.utils import compute_fuzzy_hash
from helpers.file_comparator import FileComparator


class ElfAnalyzer(Analyzer):
    def __init__(self, path, config):
        super().__init__(path, config)
        self.code_sections = []
        self.data_sections = []

    def is_empty(self):
        return not self.code_sections and not self.data_sections

    def add_section(self, section_name, flags):
        if "X" in flags:
            self.code_sections.append(section_name)
        else:
            self.data_sections.append(section_name)

    def run(self):
        section_output = ElfSectionCommand.run(self.path, self.config, self.data_sections)
        code_output = ElfCodeSectionCommand.run(self.path, self.config, self.code_sections)
        return itertools.chain(section_output, code_output)


class ElfSectionCommand(Command):
    @classmethod
    def make_regex(self, path):
        path_dir = re.escape(os.path.dirname(path).encode("utf-8"))
        path = re.escape(path.encode("utf-8"))
        regex_list = []

        # Order matters:
        # First match the full path to the file
        regex_list.append(Regex(rb"%s\b" % path, b"/file"))

        # Then match the directory containing the file
        regex_list.append(Regex(rb"%s\b" % path_dir, b"/"))

        # Finally, match every hex value (possible offset or address)
        regex_list.append(Regex(rb"0x[0-9a-f]+", b"0x"))

        return regex_list

    @classmethod
    def cmd_options(self):
        return ["--decompress"]

    @classmethod
    def make_cmd(self, file, config, sections):
        # Don't run a command if there are no sections
        if not sections:
            return

        cmd = self.cmd_options()

        # Join all section names together to dump all at once
        for section in sections:
            cmd += ["--hex-dump", section]

        return ["readelf", *cmd, file]

    @classmethod
    @Profiler.profilable
    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs)


class ElfCodeSectionCommand(Command):
    @classmethod
    def make_regex(self, path):
        regex_list = []

        # Match the full path to the file
        path = re.escape(path.encode("utf-8"))
        regex_list.append(Regex(rb"%s\b" % path, b"/file"))

        # Match the leading hex value (offset of the instruction)
        regex_list.append(Regex(rb"^\s*[0-9a-f]+:\s*", b""))

        # Match addresses that have been resolved to a symbol
        # First, parse lines that look like:
        # "callq 4f60 <call_gmon_start>"
        regex_list.append(Regex(rb"\b([0-9a-f]+)(?=\s+\<\S+\>)", b""))

        # Then, parse lines that look like:
        # "lea  0x111cb4 (%rip),%rsi     # 12a012 <_fini+0xc4>"
        regex_list.append(Regex(rb"\b(0x[0-9a-f]+)\b(?=.*\<\S+\>)", b"0x"))

        return regex_list

    @classmethod
    def cmd_options(self):
        return ["--disassemble", "--demangle", "--reloc", "--no-show-raw-insn"]

    @classmethod
    def make_cmd(self, file, config, sections):
        # Don't run a command if there are no sections
        if not sections:
            return

        cmd = self.cmd_options()

        # Join all section names together to dump all at once
        for section in sections:
            cmd += ["-j", section]

        exec = config.binutils_prefix + "objdump"
        return [exec, *cmd, file]

    @classmethod
    @Profiler.profilable
    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs)


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
        # Special names for sections with errors
        "<no-strings>",
        "<corrupt>"
    ]

    @cached_property
    def fuzzy_hash(self):
        # Compute the hash on the whole file, as it saves time and it's pretty
        # unnecessary to compute the hash on only some sections
        return compute_fuzzy_hash(self, self.path)

    def has_same_content_as(self, other):
        # For ELF files, since objdump and readelf are pretty slow, first
        # do a quicker compare before calling those tools
        quick_compare = FileComparator._compare_files(
            self, self.path,
            other, other.path
        )

        if quick_compare:
            # Since both files are exactly the same, there is not need to
            # compare any further
            return True

        # Files seem different, but maybe they're not really, so call
        # readelf and objdump
        return FileComparator._compare_files(
            self, self._comparable_path,
            other, other._comparable_path
        )

    @cached_property
    def _comparable_path(self):
        # Use readelf and objdump to extract the useful info and write it to
        # a temporary file
        tmp_file_path = FileComparator.tmp_file_path()
        absolute_path = self.path.absolute().as_posix()

        self._code_sections = []
        self._data_sections = []
        self._load_sections(absolute_path)

        # If there were no sections, default to comparing the whole file
        if self._analyzer.is_empty():
            return self.path

        with open(tmp_file_path, "wb") as tmp:
            for line in self._analyzer.run():
                tmp.write(line)

        return tmp_file_path

    def _should_skip_section(self, name, type):
        return name not in self.KEEP_SECTIONS

    @Profiler.profilable
    def _load_sections(self, file):
        """
        Inspired by diffoscope/comparator/elf.py ElfContainer
        """
        self._analyzer = ElfAnalyzer(file, self.config)

        # Get all the sections in this file to pass them to the analyzer
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
            for line in output:
                if line.startswith("Key to Flags"):
                    break

                # Strip number column because there may be spaces in the brakets
                line = line.split("]", 1)[1].split()
                name, type, flags = line[0], line[1], line[6]

                if self._should_skip_section(name, type):
                    continue

                self._analyzer.add_section(name, flags)
        except Exception as e:
            Logger.error("error in _load_sections", e)
            pass
