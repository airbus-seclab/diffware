# -*- coding: utf-8 -*-
#
# Modified version of the file included in the diffoscope project
# (https://diffoscope.org). A copy of the license is included below:
#
# diffoscope: in-depth comparison of files, archives, and directories
#
# Copyright © 2020 Jean-Romain Garnier <salsa@jean-romain.com>
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

import re
import sys
import abc
import logging

from .utils.file import File
from .utils.operation import Operation
from .utils.container import Container

from diffoscope.config import Config
from diffoscope.difference import Difference
from diffoscope.excludes import operation_excluded
from diffoscope.tools import (
    tool_required,
    tool_check_installed,
    python_module_missing,
)

try:
    import tlsh
except:
    tlsh = None

try:
    import r2pipe
except:
    python_module_missing("r2pipe")
    r2pipe = None


logger = logging.getLogger(__name__)


if not tool_check_installed("radare2"):
    r2pipe = None
    logger.debug("radare2 not found, disabling decompiler")


class Decompile(Operation, metaclass=abc.ABCMeta):
    def __init__(self, file, *args, **kwargs):
        super().__init__(file.path, *args, **kwargs)
        self.file = file

    def start(self):
        logger.debug("Executing %s", self.full_name())
        if not isinstance(self.file, AsmFunction):
            self._stdout = ""
            return

        self._decompile()

    @abc.abstractmethod
    def _decompile(self):
        raise NotImplementedError()

    def should_show_error(self):
        return False

    @property
    def output(self):
        return self._stdout.encode("utf-8").splitlines(True)


class DecompileGhidra(Decompile):
    # Basically every single one of theses regex can be removed if a
    # "0x[0-9a-f]+" is added
    # Is it really worth it to keep them? We don't want to miss some length
    # constant being changed to fix a buffer overflow for example, so
    # probably...

    # Remove addresses from comments as they can create a lot of irrelevant noise
    COMMENT_RE = re.compile(rb"(^\s*// .*)(0x[0-9a-f]+)")

    # Remove any raw address that is being accessed, for example:
    # *(int32_t *)0x38c74
    # (**(code **)0x10a500)();
    # *(int32_t *)(unaff_EBX + 0x623b)
    # *(code **)(iVar2 + 0x6127)
    # ppcVar2 = (code **)(unaff_EBX + 0x30a2);
    # *(undefined4 *)(param_1 * 4 + 0x80c59d8)
    POINTER_RE = re.compile(
        rb"(\([a-zA-Z0-9 _\*]+\*\)[\(a-zA-Z0-9_ +\-\*]*)(0x[0-9a-f]+)"
    )

    # Remove section sizes from comments
    SECTION_SIZE_RE = re.compile(rb"(\/\/ .*size )[0-9]+")

    # Remove extraout offsets
    EXTRAOUT_RE = re.compile(rb"(extraout_[A-Z]+ [ \+\-]*)0x[0-9a-f]+")

    # Remove unaff register offsets
    # unaff_EBX + 0xfff
    # (**(code **)(unaff_r30 + -0xfff))();
    UNAFF_OFFSET_RE = re.compile(rb"(unaff_[A-Za-z0-9]+ [\+\-]\s*)\-?(0x)?[0-9a-f]+")

    # Remove unaff register name
    UNAFF_RE = re.compile(rb"unaff_[A-Za-z0-9]+")

    # Remove goto and label offsets
    LABEL_RE = re.compile(rb"(?<=code_r)0x[0-9a-f]+")

    # Remove auto-generated function names
    FCN_RE = re.compile(rb"fcn\.[0-9a-f]+")
    FUNC_RE = re.compile(rb"func_0x[0-9a-f]+")

    def _run_r2_command(self):
        self.file.decompiler.jump(self.file.offset)
        output = self.file.decompiler.r2.cmdj("pdgj")

        if not output:
            # Output is None if the pdg command doesn't exist
            output = {
                "errors": [
                    'Missing r2ghidra-dec, install it with "r2pm install r2ghidra-dec"'
                ]
            }

        return output

    @tool_required("radare2")
    def _decompile(self):
        ghidra_output = self._run_r2_command()

        try:
            self._stdout = ghidra_output["code"]
        except KeyError:
            # Show errors on stdout so a failed decompilation for 1 function
            # doesn't stop the diff for the whole file
            self._stdout = "\n".join(ghidra_output["errors"])
            logger.debug(
                "r2ghidra decompiler error for %s: %s",
                self.file.signature,
                self._stdout,
            )

    def name(self):
        return "r2ghidra"

    def full_name(self, *args, **kwargs):
        return "radare2 r2ghidra"

    def filter(self, line):
        line = self.COMMENT_RE.sub(rb"\g<1>0xXXX", line)
        line = self.SECTION_SIZE_RE.sub(rb"\g<1>XXX", line)
        line = self.EXTRAOUT_RE.sub(rb"\g<1>0xXXX", line)
        line = self.UNAFF_OFFSET_RE.sub(rb"\g<1>0xXXX", line)
        line = self.UNAFF_RE.sub(rb"unaff_reg", line)
        line = self.LABEL_RE.sub(rb"0xXXX", line)
        line = self.POINTER_RE.sub(rb"\g<1>0xXXX", line)
        line = self.FCN_RE.sub(rb"fcn.XXX", line)
        return self.FUNC_RE.sub(rb"func_0xXXX", line)


class DecompileRadare2(Decompile):
    """
    Significantly faster than the ghidra decompiler, but still outputs assembly
    code, with added comments to make it more readable
    """

    # Remove addresses in comments
    # e.g. "//CALL XREF from sym._init @ 0x39b3"
    COMMENT_RE = re.compile(rb"(^\s*//.*)(0x[0-9a-f]+)")

    # Remove offsets which have been resolved
    # e.g. "ebx += 0x35b6 //section .got.plt"
    # but not "goto 0x6884 //likely"
    OFFSET_RE = re.compile(rb"0x[0-9a-f]+(?=.*//.*\..*)")

    # Remove auto-generated function names
    FCN_RE = re.compile(rb"fcn\.[0-9a-f]+")

    def _run_r2_command(self):
        self.file.decompiler.jump(self.file.offset)
        return self.file.decompiler.r2.cmd("pdc")

    @tool_required("radare2")
    def _decompile(self):
        self._stdout = self._run_r2_command()

    def name(self):
        return "disass"

    def full_name(self, *args, **kwargs):
        return "radare2 disass"

    def filter(self, line):
        line = self.COMMENT_RE.sub(rb"\g<1>0xX", line)
        line = self.OFFSET_RE.sub(rb"0xXXX", line)
        return self.FCN_RE.sub(rb"fcn.XXX", line)


class AsmFunction(File):
    DESCRIPTION = "ASM Function"

    # Mapping between the Config().decompiler option and the command class
    DECOMPILE_OPERATIONS = [
        DecompileGhidra,
        DecompileRadare2,
    ]

    def __init__(self, decompiler, data_dict):
        super().__init__(container=decompiler)
        self.data_dict = data_dict
        self.decompiler = decompiler
        self._name = self.func_name

    @property
    def name(self):
        # Multiple functions can have the same name but a different signature,
        # so use the signature as name for diffoscope
        return self.signature

    @property
    def progress_name(self):
        return "{} [{}]".format(
            self.container.source.progress_name, super().progress_name
        )

    @property
    def path(self):
        return self.container.source.path

    def is_directory(self):
        return False

    def is_symlink(self):
        return False

    def is_device(self):
        return False

    if tlsh:

        @property
        def fuzzy_hash(self):
            if not hasattr(self, "_fuzzy_hash"):
                try:
                    hex_digest = tlsh.hash(self.asm.encode())
                except ValueError:
                    # File must contain a certain amount of randomness
                    return None

                # For short files, the hex_digest is an empty string, so turn
                # it into None
                self._fuzzy_hash = hex_digest or None

            return self._fuzzy_hash

    def has_same_content_as(self, other):
        logger.debug("has_same_content: %s %s", self, other)
        try:
            return self.hex_dump == other.hex_dump
        except AttributeError:
            # 'other' is not a function.
            logger.debug("has_same_content: Not an asm function: %s", other)
            return False

    @classmethod
    def recognizes(cls, file):
        # No file should be recognized as an asm function
        return False

    def compare(self, other, source=None):
        """
        Override file's compare method to get rid of the binary diff fallback,
        as it would be redundant with other outputs
        """
        details = self.compare_details(other, source)
        details = [x for x in details if x]
        if not details:
            return None

        difference = Difference(None, self.name, other.name, source=source)
        difference.add_details(details)
        return difference

    def compare_details(self, other, source=None):
        return [
            Difference.from_operation(x, self, other)
            for x in list(self.DECOMPILE_OPERATIONS)
        ]

    @property
    def func_name(self):
        return self.data_dict["name"]

    @property
    def offset(self):
        return self.data_dict["offset"]

    @property
    def size(self):
        return self.data_dict["size"]

    @property
    def signature(self):
        return self.data_dict["signature"]

    @property
    def hex_dump(self):
        if not hasattr(self, "_hex_dump"):
            self._hex_dump = self.decompiler.dump(self.offset, self.size)

        return self._hex_dump

    @property
    def asm(self):
        if not hasattr(self, "_asm"):
            ops = self.decompiler.disassemble(self.offset)

            self._asm = ""
            for instr in ops:
                try:
                    self._asm += instr["disasm"] + "\n"
                except KeyError:
                    # Invalid instruction
                    self._asm += "invalid\n"

        return self._asm


def all_decompile_operations_are_excluded(file):
    for klass in AsmFunction.DECOMPILE_OPERATIONS:
        name = " ".join(klass(file).full_name())
        if not operation_excluded(name):
            return False

    return True


class DecompilableContainer(Container):
    auto_diff_metadata = False

    # Don't use @tool_required here so subclassing DecompilableContainer
    # doesn't block the new subclass from doing its work if radare2
    # isn't installed
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.debug("Creating DecompileContainer for %s", self.source.path)

        self._functions = {}

        # Skip disassembly (and decompilation) if a dependency is missing
        # or if radare2 commands are excluded
        if r2pipe is None or all_decompile_operations_are_excluded(self.source):
            return

        # Use "-2" flag to silence radare2 warnings
        self.r2 = r2pipe.open(self.source.path, flags=["-2"])

        # Run radare2 command which finds the functions in the executable
        self.r2.cmd("aa")  # Analyse all

        # Hide offset in asm as it serves the same purpose as line numbers,
        # which shouldn't be diffed
        self.r2.cmd("e asm.offset = false")

        # In hex dump of function, hide everything but the hex values
        self.r2.cmd("e hex.offset = false;e hex.header = false;e hex.ascii = false")

        # Use radare2 to get the list of functions
        # If there aren't any, cmdj returns None
        functions = self.r2.cmdj("aj") or []
        for f in functions:
            func = AsmFunction(self, f)
            self._functions[func.signature] = func
            logger.debug("Adding function %s", func.signature)

    def cleanup(self):
        self.r2.quit()

    def get_member_names(self):
        return self._functions.keys()

    def get_member(self, member_name):
        return self._functions[member_name]

    def jump(self, offset):
        self.r2.cmd("s {}".format(offset))

    def dump(self, offset, size):
        self.jump(offset)
        return self.r2.cmd("px {}".format(size)).strip()

    def disassemble(self, offset):
        self.jump(offset)
        return self.r2.cmdj("pdfj")["ops"]
