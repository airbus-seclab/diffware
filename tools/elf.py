# -*- coding: utf-8 -*-
#
# diffoscope: in-depth comparison of files, archives, and directories
#
# Copyright © 2014-2015 Jérémy Bobbio <lunar@debian.org>
# Copyright © 2015-2020 Chris Lamb <lamby@debian.org>
#
# diffoscope is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# diffoscope is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with diffoscope.  If not, see <https://www.gnu.org/licenses/>.

import os
import re
import logging
import subprocess
import collections

from diffoscope.exc import OutputParsingError
from diffoscope.tools import get_tool_name, tool_required
from diffoscope.config import Config
from diffoscope.tempfiles import get_named_temporary_file
from diffoscope.difference import Difference

from .deb import DebFile, get_build_id_map
from .utils.file import File
from .utils.command import Command, our_check_output
from .utils.decompile import DecompilableContainer


DEBUG_SECTION_GROUPS = (
    "rawline",
    "info",
    "abbrev",
    "pubnames",
    "aranges",
    "macro",
    "frames",
    "loc",
    "ranges",
    "pubtypes",
    "trace_info",
    "trace_abbrev",
    "trace_aranges",
    "gdb_index",
)

logger = logging.getLogger(__name__)


class Readelf(Command):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_regex()

    @tool_required("readelf")
    def cmdline(self):
        return (
            [get_tool_name("readelf"), "--wide"]
            + self.readelf_options()
            + [self.path]
        )

    def readelf_options(self):
        return []  # noqa

    def filter(self, line):
        # we don't care about the name of the archive
        line = self._archive_re.sub("File: lib.a(", line)
        # the full path can appear in the output, we need to remove it
        line = self._path_re.sub("/", line)
        # each section type can edit some output lines
        return self.filter_stdout(line)

    @staticmethod
    def should_skip_section(section_name, section_type):
        return False

    def _init_regex(self):
        """
        Create and compile regex to filter output lines
        """
        # we don't care about the name of the archive
        path_dir = re.escape(os.path.dirname(self.path).encode("utf-8"))
        path = re.escape(self.path.encode("utf-8"))
        self._path_re = re.compile(rb"\b%s/\b" % path_dir)
        self._archive_re = re.compile(rb"^File: %s\(" % path)

        # We don't care about offsets
        # self._filter_re = re.compile(rboffset 0x[0-9a-f]+)
        self._filter_re = re.compile(rb"\b0x[0-9a-f]+\b")

        # In case subclasses have custom regex
        self.init_regex()

    def init_regex(self):
        """
        Method to override
        """
        pass

    def filter_stdout(self, line):
        """
        Default method, to override if necessary
        Replaces hex offsets in strings like "offset 0x???"
        """
        # Remove messages referencing an offset
        return self._filter_re.sub(b"", line)

    @property
    def stdout(self):
        return self._process.stdout.splitlines(True)


class ReadelfFileHeader(Readelf):
    def readelf_options(self):
        return ["--file-header"]

    def init_regex(self):
        self._entry_re = re.compile(rb"(Entry point address:\s+)0x[0-9a-f]+")
        self._size_re = re.compile(rb"[0-9]+ \(bytes( into file)?\)")

    def filter_stdout(self, line):
        line = super().filter_stdout(line)
        line = self._entry_re.sub(rb"\g<1>0xXXX", line)
        return self._size_re.sub(b"", line)


class ReadelfProgramHeader(Readelf):
    def readelf_options(self):
        return ["--program-header"]

    def init_regex(self):
        self._addr_re = re.compile(rb"0x[0-9a-f]*")

    def filter_stdout(self, line):
        # No need to call super as this is more strict
        return self._addr_re.sub(b"", line)


class ReadelfSections(Readelf):
    def readelf_options(self):
        return ["--sections"]

    def init_regex(self):
        # Lines look like this:
        # "  [Nr] Name    Type     Address           Off      Size     [...]"
        # "  [ 1] interp  PROGBITS 0000000000400238  000238   00001c   [...]"
        start_regex = rb"\s*\[\s*[0-9]+\] "  # Match "  [  1] "
        column_regex = rb"\S+\s+"  # Match any column
        hex_regex = rb"[0-9a-f]+"  # Match hex value without 0x

        # We want to get rid of the address and offset
        addr_regex = rb"(^%b%b)%b" % (start_regex, 2 * column_regex, hex_regex)
        offset_regex = rb"(^%b%b)%b" % (
            start_regex,
            3 * column_regex,
            hex_regex,
        )
        size_regex = rb"(^%b%b)%b" % (start_regex, 4 * column_regex, hex_regex)

        # Compile to save time
        self._addr_re = re.compile(addr_regex)
        self._offset_re = re.compile(offset_regex)
        self._size_re = re.compile(size_regex)

    def filter_stdout(self, line):
        # Take care of the last column first, just in case we mess up the format
        line = self._size_re.sub(rb"\g<1>XXXXXX", line)
        line = self._offset_re.sub(rb"\g<1>XXXXXX", line)
        return self._addr_re.sub(rb"\g<1>XXXXXXXXXXXXXXXX", line)


class ReadelfSymbols(Readelf):
    def readelf_options(self):
        return ["--symbols"]

    @staticmethod
    def should_skip_section(section_name, section_type):
        return section_type in {"DYNSYM", "SYMTAB"}

    def init_regex(self):
        # Lines look like this:
        # "  Num: Value             Size     Type   [...]"
        # "    1: 000000000040f860  22       FUNC   [...]"
        start_regex = rb"\s*[0-9]+:\s+"  # Match "  1: "
        hex_regex = rb"[0-9a-f]+"  # Match hex value without 0x

        # We want to get rid of the size and address
        addr_regex = rb"(^%b)%b" % (start_regex, hex_regex)
        size_regex = rb"(^%b%b)\s+[0-9]+" % (start_regex, hex_regex)

        # Compile to save time
        self._addr_re = re.compile(addr_regex)
        self._size_re = re.compile(size_regex)

    def filter_stdout(self, line):
        line = super().filter_stdout(line)
        line = self._size_re.sub(rb"\g<1> XXX ", line)
        return self._addr_re.sub(rb"\g<1>XXXXXXXXXXXXXXXX ", line)


class ReadelfRelocs(Readelf):
    def readelf_options(self):
        return ["--relocs"]

    @staticmethod
    def should_skip_section(section_name, section_type):
        return section_type in {"REL", "RELA"}

    def init_regex(self):
        # Lines look like this:
        # "  Offset           Info             Type               Symbol's Value    Symbol's Name + Addend [...]"
        # "  00000000005623b0 0000002d00000006 R_X86_64_GLOB_DAT  0000000000000000  .debug_str + 7ca9      [...]"
        column_regex = rb"\S+\s+"  # Match any column
        hex_regex = rb"[0-9a-f]+"  # Match hex value without 0x
        hex_column_regex = rb"%b\s+" % (hex_regex)  # Match a column with a hex

        # We want to get rid of the address and offset
        offset_regex = rb"^%b" % (hex_regex)
        info_regex = rb"(^%b)%b" % (hex_column_regex, hex_regex)
        value_regex = rb"(^%b)%b" % (
            2 * hex_column_regex + column_regex,
            hex_regex,
        )
        addend_regex = rb"(^%b)(\..*\s\+\s)%b" % (
            2 * hex_column_regex + column_regex + hex_column_regex,
            hex_regex,
        )

        # Compile to save time
        self._offset_re = re.compile(offset_regex)
        self._info_re = re.compile(info_regex)
        self._value_re = re.compile(value_regex)
        self._addend_re = re.compile(addend_regex)

    def filter_stdout(self, line):
        line = super().filter_stdout(line)
        # Take care of the last column first, just in case we mess up the format
        line = self._addend_re.sub(rb"\g<1>\g<2>XXXX", line)
        line = self._value_re.sub(rb"\g<1>XXXXXXXXXXXXXXXX", line)
        line = self._info_re.sub(rb"\g<1>XXXXXXXXXXXXXXXX", line)
        return self._offset_re.sub(rb"XXXXXXXXXXXXXXXX", line)


class ReadelfDynamic(Readelf):
    def readelf_options(self):
        return ["--dynamic"]

    @staticmethod
    def should_skip_section(section_name, section_type):
        return section_type == "DYNAMIC"

    def init_regex(self):
        self._addr_re = re.compile(rb"0x[0-9a-f]+")
        self._size_re = re.compile(rb"[0-9]+ \(bytes\)")

    def filter_stdout(self, line):
        # Remove sizes (no need to call super as this takes care or more)
        line = self._addr_re.sub(b"", line)
        return self._size_re.sub(b"X (bytes)", line)


class ReadelfNotes(Readelf):
    def readelf_options(self):
        return ["--notes"]

    @staticmethod
    def should_skip_section(section_name, section_type):
        return section_type == "NOTE"


class ReadelfVersionInfo(Readelf):
    def readelf_options(self):
        return ["--version-info"]

    @staticmethod
    def should_skip_section(section_name, section_type):
        return section_type in {"VERDEF", "VERSYM", "VERNEED"}

    def init_regex(self):
        self._filter_re = re.compile(rb"[0-9]\s\(\*(global|local)\*\)")

    def filter_stdout(self, line):
        # Remove sizes (no need to call super)
        return self._filter_re.sub(b"X (* XXX *)", line)


class ReadelfDebugDump(Readelf):
    def readelf_options(self):
        return ["--debug-dump=%s" % self._debug_section_group]


READELF_DEBUG_DUMP_COMMANDS = [
    type(
        "ReadelfDebugDump_{}".format(x),
        (ReadelfDebugDump,),
        {"_debug_section_group": x},
    )
    for x in DEBUG_SECTION_GROUPS
]


class ReadElfSection(Readelf):
    @staticmethod
    def base_options():
        if not hasattr(ReadElfSection, "_base_options"):
            output = our_check_output(
                [get_tool_name("readelf"), "--help"],
                stderr=subprocess.DEVNULL,
            ).decode("us-ascii", errors="replace")

            ReadElfSection._base_options = []
            for x in ("--decompress",):
                if x in output:
                    ReadElfSection._base_options.append(x)
        return ReadElfSection._base_options

    def __init__(self, path, section_name, *args, **kwargs):
        self._path = path
        self._section_name = section_name
        super().__init__(path, *args, **kwargs)

    @property
    def section_name(self):
        return self._section_name

    def readelf_options(self):
        return ReadElfSection.base_options() + [
            "--hex-dump={}".format(self.section_name)
        ]


class ReadelfStringSection(ReadElfSection):
    def readelf_options(self):
        return ReadElfSection.base_options() + [
            "--string-dump={}".format(self.section_name)
        ]


class ObjdumpSection(Command):
    def __init__(self, path, section_name, *args, **kwargs):
        self._path = path
        self._path_bin = path.encode("utf-8")
        self._section_name = section_name
        super().__init__(path, *args, **kwargs)
        self.init_regex()

    def objdump_options(self):
        return []

    @tool_required("objdump")
    def cmdline(self):
        return (
            [get_tool_name("objdump")]
            + self.objdump_options()
            + ["--section={}".format(self._section_name), self.path]
        )

    def filter(self, line):
        # Remove the filename from the output
        if line.startswith(self._path_bin + b":"):
            return b""
        if line.startswith(b"In archive"):
            return b""

        return self.filter_stdout(line)

    def init_regex(self):
        # Remove the leading hex value (offset of the instruction)
        self._line_re = re.compile(rb"^\s*[0-9a-f]+:\s*")
        # Remove addresses that have been resolved to a symbol
        # First, parse lines that look like:
        # "callq 80487e0 print_usage(char const*)"
        self._resolved_re = re.compile(rb"\b([0-9a-f]+)(?=\s+\<.+\>)")
        # Then, parse lines that look like:
        # "lea  0x111cb4 (%rip),%rsi     # 12a012 <_fini+0xc4>"
        self._pointer_re = re.compile(rb"\b(0x[0-9a-f]+)\b(?=.*\<.+\>)")
        # Remove all hex values
        self._filter_re = re.compile(rb"\b0x[0-9a-f]+\b")

    def filter_stdout(self, line):
        line = self._line_re.sub(b"", line)
        line = self._resolved_re.sub(b"XXX", line)
        # return self._pointer_re.sub(b"0xXXX ", line)
        return self._filter_re.sub(b"0xX", line)


class ObjdumpDisassembleSection(ObjdumpSection):
    RE_SYMBOL_COMMENT = re.compile(
        rb"^( +[0-9a-f]+:[^#]+)# [0-9a-f]+ <[^>]+>$"
    )

    def objdump_options(self):
        # With "--line-numbers" we get the source filename and line within the
        # disassembled instructions.
        # objdump can get the debugging information from the elf or from the
        # stripped symbols file specified in the .gnu_debuglink section
        return [
            "--line-numbers",
            "--disassemble",
            "--demangle",
            "--reloc",
            "--no-show-raw-insn",
            "--source",
        ]

    def filter_stdout(self, line):
        line = super().filter_stdout(line)
        return ObjdumpDisassembleSection.RE_SYMBOL_COMMENT.sub(r"\1", line)


class ObjdumpDisassembleSectionNoLineNumbers(ObjdumpDisassembleSection):
    def objdump_options(self):
        return ["--disassemble", "--demangle", "--no-show-raw-insn"]


READELF_COMMANDS = (
    ReadelfFileHeader,
    ReadelfProgramHeader,
    # ReadelfSections,
    # ReadelfSymbols,
    ReadelfRelocs,
    ReadelfDynamic,
    # ReadelfNotes,
    # ReadelfVersionInfo
)


def _compare_elf_data(path1, path2):
    return [
        Difference.from_command(x, path1, path2, ignore_returncodes={1})
        for x in list(READELF_COMMANDS)
    ]


IGNORE_SECTIONS = [
    ".hash",
    ".gnu.hash",
    ".strtab",
    ".shstrtab",
    ".got",
    ".plt",
    ".got2",
    ".got.plt",
    ".eh_frame",
    ".eh_frame_hdr",
    ".dynstr",
    ".gnu.version",
    ".gnu.version_d",
    ".gnu.version_r",
    ".gnu_debuglink",
    ".note.gnu.build-id",
    ".data",
    ".rodata",
    ".rodata.str1.4",
    ".data.rel.ro",
    ".dynsym",
    ".symtab",
    ".gcc_except_table",
    ".ctors",
    ".dtors",
    ".jcr",
    ".init_array",
    ".fini_array",
    ".gnu_debugaltlink",
    ".ARM.extab",
    ".ARM.exidx",
]


def _should_skip_section(name, type):
    for x in READELF_COMMANDS:
        if x.should_skip_section(name, type):
            logger.debug("Skipping section %s, covered by %s", name, x)
            return True

    if name.startswith(".debug") or name.startswith(".zdebug"):
        return True

    if name in IGNORE_SECTIONS:
        return True

    return False


class ElfSection(File):
    def __init__(self, elf_container, member_name):
        super().__init__(container=elf_container)
        self._name = member_name

    @property
    def name(self):
        return self._name

    @property
    def progress_name(self):
        return "{} [{}]".format(
            self.container.source.progress_name, super().progress_name
        )

    @property
    def path(self):
        return self.container.source.path

    def cleanup(self):
        pass

    def is_directory(self):
        return False

    def is_symlink(self):
        return False

    def is_device(self):
        return False

    def has_same_content_as(self, other):
        # Always force diff of the section
        return False

    @property
    def fuzzy_hash(self):
        return None

    @classmethod
    def recognizes(cls, file):
        # No file should be recognized as an elf section
        return False

    def compare(self, other, source=None):
        return Difference.from_command(
            ReadElfSection, self.path, other.path, command_args=[self._name]
        )


class ElfCodeSection(ElfSection):
    def compare(self, other, source=None):
        # Disassemble with line numbers, but if the command is excluded or
        # fails, fallback to disassembly. If that is also excluded or failing,
        # only then fallback to a hexdump.
        diff = None
        error = None
        try:
            diff, excluded = Difference.from_command_exc(
                ObjdumpDisassembleSection,
                self.path,
                other.path,
                command_args=[self._name],
            )
        except subprocess.CalledProcessError as e:
            # eg. When failing to disassemble a different architecture.
            error = e
            logger.error(e)

        if not error and not excluded:
            return diff

        try:
            diff, excluded = Difference.from_command_exc(
                ObjdumpDisassembleSectionNoLineNumbers,
                self.path,
                other.path,
                command_args=[self._name],
            )
        except subprocess.CalledProcessError as e:
            error = e
            logger.error(e)

        if not error and not excluded:
            return diff

        return super().compare(other, source)


class ElfStringSection(ElfSection):
    def compare(self, other, source=None):
        return Difference.from_command(
            ReadelfStringSection,
            self.path,
            other.path,
            command_args=[self._name],
        )


@tool_required("readelf")
def get_build_id(path):
    try:
        output = our_check_output(
            [get_tool_name("readelf"), "--notes", path],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        logger.debug("Unable to get Build ID for %s: %s", path, e)
        return None

    m = re.search(
        r"^\s+Build ID: ([0-9a-f]+)$",
        output.decode("utf-8"),
        flags=re.MULTILINE,
    )
    if not m:
        return None

    return m.group(1)


@tool_required("readelf")
def get_debug_link(path):
    try:
        output = our_check_output(
            [get_tool_name("readelf"), "--string-dump=.gnu_debuglink", path],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        logger.debug("Unable to get Build Id for %s: %s", path, e)
        return None

    m = re.search(
        r"^\s+\[\s+0\]\s+(\S+)$",
        output.decode("utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    if not m:
        return None

    return m.group(1)


class ElfContainer(DecompilableContainer):
    auto_diff_metadata = False

    SECTION_FLAG_MAPPING = {
        "X": ElfCodeSection,
        "S": ElfStringSection,
        "_": ElfSection,
    }

    @tool_required("readelf")
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.debug("Creating ElfContainer for %s", self.source.path)

        cmd = [
            get_tool_name("readelf"),
            "--wide",
            "--section-headers",
            self.source.path,
        ]
        output = our_check_output(cmd, shell=False, stderr=subprocess.DEVNULL)
        has_debug_symbols = False

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

                if name.startswith(".debug") or name.startswith(".zdebug"):
                    has_debug_symbols = True

                if _should_skip_section(name, type):
                    continue

                # Use first match, with last option being _ as fallback
                elf_class = [
                    ElfContainer.SECTION_FLAG_MAPPING[x]
                    for x in flags
                    if x in ElfContainer.SECTION_FLAG_MAPPING
                ][0]

                logger.debug(
                    "Adding section %s (%s) as %s", name, type, elf_class
                )
                self._sections[name] = elf_class(self, name)

        except Exception as e:
            command = " ".join(cmd)
            logger.debug(
                "OutputParsingError in %s from `%s` output - %s:%s",
                self.__class__.__name__,
                command,
                e.__class__.__name__,
                e,
            )
            raise OutputParsingError(command, self)

        if not has_debug_symbols:
            self._install_debug_symbols()

    @tool_required("objcopy")
    def _install_debug_symbols(self):
        if Config().use_dbgsym == "no":
            return

        # Figure out if we are in a Debian package first
        try:
            deb = (
                self.source.container.source.container.source.container.source
            )
        except AttributeError:
            return

        # It needs to be a .deb and we need access a to a -dbgsym package in
        # the same .changes, directory or archive
        if not isinstance(deb, DebFile) or not deb.container:
            return

        # If the .deb in question is the top-level of the source we have passed
        # a .deb directly to diffoscope (versus finding one specified in a
        # .changes or .buildinfo file). In this case, don't automatically
        # search for a -dbgsym file unless the user specified
        # `Config().use_dbgsym`.
        if (
            not hasattr(deb.container.source, "container")
            and Config().use_dbgsym != "yes"
        ):
            return

        # Retrieve the Build ID for the ELF file we are examining
        build_id = get_build_id(self.source.path)
        debuglink = get_debug_link(self.source.path)
        if not build_id or not debuglink:
            return

        logger.debug(
            "Looking for a dbgsym package for Build Id %s (debuglink: %s)",
            build_id,
            debuglink,
        )

        # Build a map of Build-Ids if it doesn't exist yet
        if not hasattr(deb.container, "dbgsym_build_id_map"):
            deb.container.dbgsym_build_id_map = get_build_id_map(deb.container)

        if build_id not in deb.container.dbgsym_build_id_map:
            logger.debug(
                "Unable to find a matching debug package for Build Id %s",
                build_id,
            )
            return

        dbgsym_package = deb.container.dbgsym_build_id_map[build_id]
        debug_file_path = "./usr/lib/debug/.build-id/{0}/{1}.debug".format(
            build_id[:2], build_id[2:]
        )
        debug_file = dbgsym_package.as_container.data_tar.as_container.lookup_file(
            debug_file_path
        )
        if not debug_file:
            logger.debug(
                "Unable to find the matching debug file %s in %s",
                debug_file_path,
                dbgsym_package,
            )
            return

        # Create a .debug directory and link the debug symbols there with the
        # right name
        dest_path = os.path.join(
            os.path.dirname(self.source.path),
            ".debug",
            os.path.basename(debuglink),
        )
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        def objcopy(*args):
            our_check_output(
                (get_tool_name("objcopy"),) + args,
                shell=False,
                stderr=subprocess.DEVNULL,
            )

        # If #812089 was fixed, we would just do os.link(debug_file.path,
        # dest_path) but for now, we need to do more complicated things…
        # 1. Use objcopy to create a file with only the original .gnu_debuglink
        # section as we will have to update it to get the CRC right.
        debuglink_path = get_named_temporary_file(
            prefix="{}.debuglink.".format(self.source.path)
        ).name

        objcopy(
            "--only-section=.gnu_debuglink", self.source.path, debuglink_path
        )

        # 2. Monkey-patch the ElfSection object created for the .gnu_debuglink
        # to change the path to point to this new file
        section = self._sections[".gnu_debuglink"]

        class MonkeyPatchedElfSection(section.__class__):
            @property
            def path(self):
                return debuglink_path

        section.__class__ = MonkeyPatchedElfSection

        # 3. Create a file with the debug symbols in uncompressed form
        objcopy("--decompress-debug-sections", debug_file.path, dest_path)

        # 4. Update the .gnu_debuglink to this new file so we get the CRC right
        objcopy("--remove-section=.gnu_debuglink", self.source.path)
        objcopy("--add-gnu-debuglink={}".format(dest_path), self.source.path)

        logger.debug("Installed debug symbols at %s", dest_path)

    def get_member_names(self):
        decompiled_members = super().get_member_names()
        return list(decompiled_members) + list(self._sections.keys())

    def get_member(self, member_name):
        try:
            return self._sections[member_name]
        except KeyError:
            return super().get_member(member_name)


class Strings(Command):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.date_re_list = []

        # Ignore dates in the strings output
        self.date_re_list.append(
            rb"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s\d{4}(\s\d{2}:\d{2}:?\d{0,2})?"
        )
        self.date_re_list.append(
            rb"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s\d{2}:\d{2}:\d{2}\sUTC\s\d{4}"
        )
        self.date_re_list.append(
            rb"\d{2}/\d{2}/\d{2}(\s\d{2}:\d{2}:?\d{0,2})?\s?(AM|PM)?"
        )
        self.date_re_list.append(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+\d{4}")

        self.date_re_list = [
            re.compile(pattern) for pattern in self.date_re_list
        ]

    @tool_required("strings")
    def cmdline(self):
        return ("strings", "--all", "-n", "10", self.path)

    @property
    def stdout(self):
        lines = self._process.stdout.splitlines(True)

        # Filter lines before sorting them because the mask
        # may change the order
        lines = [self._filter(line) for line in lines]
        return sorted(lines)

    def _filter(self, line):
        if b"compiled at" in line:
            return b""

        for pattern in self.date_re_list:
            line = pattern.sub(b"[date]", line)

        return line


class ElfFile(File):
    DESCRIPTION = "ELF binaries"
    CONTAINER_CLASSES = [ElfContainer]
    FILE_TYPE_RE = re.compile(r"^ELF ")

    def compare(self, other, source=None):
        difference = self._compare_using_details(other, source)

        if not difference:
            return difference

        # Append any miscellaneous comments for this file.
        for x in getattr(self, "_comments", []):
            difference.add_comment(x)

        return difference

    def compare_details(self, other, source=None):
        differences = _compare_elf_data(self.path, other.path)
        differences = [x for x in differences if x is not None]

        # Don't add string differences if everything else has no diff
        if not differences:
            return differences

        differences.append(
            Difference.from_command(Strings, self.path, other.path)
        )
        return differences
