# Difftool

## Installing

### Minimal

The minimal install doesn't allow for automatic file extraction, but can work on already extracted files and directories.

`argcomplete` is used to provide autocompletion, if possible:

```bash
pip3 install argcomplete
```

`fact_helper_file` provides filemagick and config parsing helpers:

```bash
git clone https://github.com/fkie-cad/fact_helper_file.git
cd fact_helper_file
pip3 install .
```

`tlsh` enables to compute distances between files and identify moved files:

```bash
pip3 install tlsh
```

All that is left is to clone this repository:

```bash
git clone https://github.com/airbus-seclab/Difftool.git ~/difftool
cd ~/difftool
```


### Full

The full install adds an automatic extraction tool.

Install `fact_extractor` from [this branch](https://github.com/JRomainG/fact_extractor/tree/dev):

```bash
git clone https://github.com/JRomainG/fact_extractor.git ~/fact_extractor
cd ~/fact_extractor
fact_extractor/install/pre_install.sh
fact_extractor/install.py
```

Make sure the `tlsh` and `argcomplete` are installed:

```bash
pip3 install tlsh argcomplete
```

Finally, clone this repository:

```bash
git clone https://github.com/airbus-seclab/Difftool.git ~/difftool
cd ~/difftool
```

## Usage

```
./main.py -h

usage: main.py [-h] [-o DATA_FILE] [-L {DEBUG,INFO,WARNING,ERROR}] [-d] [-C CONFIG_FILE] [-j JOBS] [--exclude GLOB_PATTERN] [--exclude-mime GLOB_PATTERN] [--blacklist MIME_TYPE]
               [--fuzzy-threshold FUZZY_THRESHOLD] [--max_depth MAX_DEPTH] [--no-extract] [--no-specialize] [--no-distance] [--order-by {none,path,distance}] [--min_dist MIN_DIST]
               [--no-progress] [--clean-extracted] [--enable-statistics] [--profile]
               FILE_PATH_1 FILE_PATH_2

positional arguments:
  FILE_PATH_1           Path to first file
  FILE_PATH_2           Path to second file

optional arguments:
  -h, --help            show this help message and exit
  -o DATA_FILE, --output DATA_FILE
                        Path to file in which to write the list of files (- for stdout)
  -L {DEBUG,INFO,WARNING,ERROR}, --log_level {DEBUG,INFO,WARNING,ERROR}
                        Define the log level
  -d, --debug           Print debug messages
  -C CONFIG_FILE, --config_file CONFIG_FILE
                        Path to config File
  -j JOBS, --jobs JOBS  Number of job to run in parallel (default is number of cpus)
  --exclude GLOB_PATTERN
                        Exclude files paths that match GLOB_PATTERN.
  --exclude-mime GLOB_PATTERN
                        Exclude files with mime types that match GLOB_PATTERN.
  --blacklist MIME_TYPE
                        Exclude files with MIME_TYPE.
  --fuzzy-threshold FUZZY_THRESHOLD
                        Threshold for fuzzy-matching to detect moved files (<= 0 to disable, default is 80)
  --max_depth MAX_DEPTH
                        Maximum depth for recursive unpacking (< 0 for no limit, default is 8)
  --no-extract          Consider all files are already extracted, and only compare them
  --no-specialize       Do not use specific content comparison for known file types, but use simple binary data comparison
  --no-distance         Disable computing the distance between two modified files using TLSH
  --order-by {none,path,distance}
                        Define the sort order for the output. Note: setting this to anything other than "none" will disable progressive output
  --min_dist MIN_DIST   Ignore files with a difference lower than the one given (< 0 for no limit)
  --no-progress         Hide progress messages
  --clean-extracted     Delete temporary container files which have been extracted
  --enable-statistics   Compute statistics or check for unpack data loss
  --profile             Measure the number of calls and time spent in different methods
```

## Configuration

Most parameters can be set from the CLI and using the config file (see `config.cfg` for an example).

While settings in the `diff` section are specific to this tool, the ones in the `unpack` and `ExpertSettings` are shared with [fact_extractor](https://github.com/fkie-cad/fact_extractor), so you should check out their documentation.

Here's a list of options that can be set in the config file:

### `diff` section

| Option name      | Default value | Description                                                  |
| ---------------- | ------------- | ------------------------------------------------------------ |
| data_file        | -             | Path to file in which to write the list of files (- for stdout) |
| debug            | False         | Print debug messages                                         |
| log_level        | "INFO"        | Define the log level                                         |
| jobs             | <cpu_count>   | Number of job to run in parallel                             |
| exclude_mime     | []            | Exclude files with mime types that match the given glob pattern |
| fuzzy_threshold  | 80            | Threshold for fuzzy-matching to detect moved files (<= 0 to disable) |
| max_depth        | 8             | Maximum depth for recursive unpacking (< 0 for no limit)     |
| extract          | True          | Whether to try to unpack files                               |
| specialize       | True          | Whether to use file-specific comparison (if False, always compare file binary data) |
| compute_distance | True          | Whether to compute the distance between two modified files using TLSH |
| sort_order       | "none"        | Define the sort order for the output                         |
| min_dist         | -1            | Ignore files with a difference lower than the one given (< 0 for no limit) |
| show_progress    | True          | Whether to output progress messages in the console or not    |
| clean_extracted  | False         | Delete temporary container files which have been extracted   |
| profile          | False         | Whether to measure the number of calls and time spent in different methods |

### `unpack` section

| Option name   | Default value   | Description                                                  |
| ------------- | --------------- | ------------------------------------------------------------ |
| exclude       | []              | Exclude files with paths that match the given glob pattern   |
| blacklist     | []              | Don't attempt to unpack files with the given mime-types      |
| data_folder_1 | /tmp/extractor1 | Folder in which to unpack the data of the first file         |
| data_folder_2 | /tmp/extractor2 | Folder in which to unpack the data of the second file        |
| statistics    | False           | Whether fact_extractor should compute statistics after extracting files |

### `ExpertSettings` section

| Option name           | Default value | Description                                                  |
| --------------------- | ------------- | ------------------------------------------------------------ |
| statistics            | False         | Whether fact_extractor should compute statistics after extracting files |
| unpack_threshold      | 0.8           | Threshold to detect data loss when unpacking                 |
| header_overhead       | 256           | Size of header for unpacked data, used to detect data loss   |
| compressed_file_types | []            | List of files used when computing statistics to know whether data was lost |

## Optimizing

### Extracting

For faster analysis, you should try to avoid extracting files on every run by using the `--no-extract` option. Since the tool can work on directories, you can either manually extract the content beforehand, or run the script once and then run it again on the extracted folder.

### Specializing

Some types of files have specific comparing mechanisms to make the output more robust. As this can add significant overhead, they can be disabled using the `--no-specialize` option.

Disabling this option has the side effect of making the comparison tool follow symlinks. Though it shouldn't fail regardless of what the link points to, it may result in symlinks being reported as different and timeouts being shown while reading from them. In that case, you may want to ignore symlinks by using the `--exclude-mime inode/symlink` option.

### Ignoring files

You should also try to exclude as many files as possible, either based on their mime-type:

```
--exclude-mime audio/* --exclude-mime image/* --exclude-mime video/*
```

... or based on their path:

```
--exclude */build/* --exclude *.txt --exclude *.json
```

You can also tweak the `blacklist` option from the config file to prevent unpacking attempts of known mime-types for which it's unnecessary.

### Saving time for moved detection

If folders have been renamed (apart from the root file), try renaming them so the overall hierarchy of both files match. Otherwise, many files will have to be compared to attempt to detect the ones that have been moved.

## Tools

### Diffoscope

The output of this script can be parsed to run [diffoscope](https://diffoscope.org/) on the identified changes:

```bash
./tools/diffoscope.py path-to-output-diff
```

Any option other than the path to the file will be passed to `diffoscope`. When possible, the modified files won't be copied, but a hardlink will be created in a temporary folder.
