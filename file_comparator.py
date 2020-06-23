import os
import tempfile
import subprocess

from profiler import Profiler


class FileComparator:
    TMP_DIR = tempfile.TemporaryDirectory(prefix="difftool_")

    @staticmethod
    def are_equal(file1, file2):
        """
        Inspired by has_same_content_as in diffoscope/comparators/utils/file.py
        """
        try:
            file1_size = os.path.getsize(file1._comparable_path)
            file2_size = os.path.getsize(file2._comparable_path)
        except OSError as e:
            # Files not readable (e.g. broken symlinks) or something else,
            # just assume they are different
            return False

        if file1_size == file2_size and file2_size <= 65536:
            # Compare small files directly
            file1_content = b"".join(file1._read())
            file2_content = b"".join(file2._read())
            return file1_content == file2_content

        # Call an external diff otherwise
        return subprocess.call(
            ("cmp", "-s", file1._comparable_path, file2._comparable_path),
            shell=False,
            close_fds=True,
        ) == 0

    @classmethod
    def tmp_file_path(self):
        """
        Used to create a temporary file that should be cleaned up after the
        script is done (remember to call cleanup)
        """
        return tempfile.mktemp(dir=self.TMP_DIR.name)

    @classmethod
    def cleanup(self):
        self.TMP_DIR.cleanup()
