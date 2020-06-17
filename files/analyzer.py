import re
import subprocess

from logger import Logger
from profiler import Profiler


class Analyzer:
    def __init__(self, path):
        self.path = path

    def run(self):
        """
        Builds a generator with the filtered output lines
        of all commands that this Analyzer runs
        """
        raise NotImplementedError


class Regex:
    def __init__(self, pattern, replace):
        self.pattern = pattern
        self.replace = replace

    @property
    def pattern(self):
        return self._compiled.pattern

    @pattern.setter
    def pattern(self, pattern):
        self._compiled = re.compile(pattern)

    def apply(self, string):
        """
        Returns the string with the substrings matching self.pattern replaced
        by self.replace
        """
        return self._compiled.sub(self.replace, string)


class Command:
    @classmethod
    def make_regex(self, path):
        """
        Returns a list of Regex instances to apply to the output of this command
        """
        return []

    @classmethod
    def cmd_options(self):
        """
        Returns a list of options needed for this command
        """
        return []

    @classmethod
    def make_cmd(self, file):
        """
        Returns a list, as accepted by subprocess.run, of strings to run
        this command for the given file
        """
        raise NotImplementedError

    @classmethod
    @Profiler.profilable
    def run(self, file, *args, **kwargs):
        """
        Run this command and return a generator of filtered output lines
        """
        regex = self.make_regex(file)
        cmd = self.make_cmd(file, *args, **kwargs)

        # Handle empty commands to save some time
        if cmd is None:
            return iter(())

        Logger.debug("Running command {}".format(" ".join(cmd)))
        process = subprocess.run(
            cmd,
            shell=False,
            close_fds=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        return self._filter(process.stdout.splitlines(True), regex)

    @classmethod
    def _filter(self, output, regex):
        for line in output:
            for reg in regex:
                line = reg.apply(line)
            yield line
