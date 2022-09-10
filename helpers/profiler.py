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
import time
from functools import wraps


class Profiler():
    """
    Generator class used to profile the time spent in different functions
    """
    STATS = {}
    PROFILING_ENABLED = False

    @property
    def stats(self):
        return self.STATS

    @classmethod
    def print(cls):
        if not cls.PROFILING_ENABLED:
            return

        print("\n### Profiler stats")
        funcs = sorted(cls.STATS.keys())

        longest_column = max(len(x) for x in funcs)
        column_format = "{:<" + str(longest_column) + "}"
        row_format = column_format + "   {:<3}   {} call(s)"

        for func in funcs:
            total_time = cls.STATS[func]["total_time"]
            call_count = cls.STATS[func]["calls"]
            print(row_format.format(
                func,
                "{:.3f}s".format(total_time),
                call_count
            ))

    @classmethod
    def record_time(cls, func_name, start, end):
        if not cls.PROFILING_ENABLED:
            return

        if func_name not in cls.STATS:
            cls.STATS[func_name] = {
                "total_time": 0,
                "calls": 0
            }
        cls.STATS[func_name]["total_time"] += end - start
        cls.STATS[func_name]["calls"] += 1

    @classmethod
    def profilable(cls, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not cls.PROFILING_ENABLED:
                return func(*args, **kwargs)

            # Measure the time spent for the call, and update the stats
            start = time.time()
            value = func(*args, **kwargs)
            end = time.time()
            cls.record_time(func.__qualname__, start, end)
            return value

        return wrapper
