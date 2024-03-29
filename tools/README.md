## diffoscope.py

This script can be used to run [https://diffoscope.org/](diffoscope) on an output file generated by the tool:

```bash
./diffoscope.py path-to-output-diff
```

Additional parameters will be passed to diffoscope.

## elf.py

This file can be used to replace the `elf.py` included in diffoscope. To use it, simply [clone diffoscope](https://salsa.debian.org/reproducible-builds/diffoscope) and replace the existing file in `diffoscope/comparators/elf.py`.

Using this version of `elf.py` will reduce the output of diffoscope for elf files, by ignoring some sections and filtering the outputs of `readelf`, `objdump` and `strings` to remove as much noise as possible. It is especially useful when trying to behavior changes introduced in a new ELF file.

## decompile.py

This file can be used to replace the `decompile.py` included in diffoscope. To use it, simply [clone diffoscope](https://salsa.debian.org/reproducible-builds/diffoscope) and replace the existing file in `diffoscope/comparators/decompile.py`.

Using this version of `decompile.py` will reduce the output of diffoscope for files using the decompiler (currently only ELF files), by filtering some offsets / addresses.
