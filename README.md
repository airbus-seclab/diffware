# Difftool

## Installing

Install `fact_extractor` from [this branch](https://github.com/JRomainG/fact_extractor/tree/dev):

```
git clone https://github.com/JRomainG/fact_extractor.git ~/fact_extractor
cd ~/fact_extractor
fact_extractor/install/pre_install.sh
fact_extractor/install.py
```

Clone this repository:

```
git clone https://github.com/airbus-seclab/Difftool.git ~/difftool
cd ~/difftool
```

## Usage

```
python3 main.py -h

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
                        set path to config File
  --exclude GLOB_PATTERN
                        Exclude files paths that match GLOB_PATTERN.
  --blacklist MIME_TYPE
                        Exclude files with MIME_TYPE.
  --max_depth MAX_DEPTH
                        Maximum depth for recursive unpacking (< 0 for no limit)
  --no-extract          Consider all files are already extracted, and only compare them
  --no-specialize       Do not use specific content comparison for known file types, but use simple binary data comparison
  --no-distance         Compute the distance between two modified files using TLSH
  --order-by {none,path,distance}
                        Define the sort order for the output. Note: setting this to anything other than "none" will disable progressive output
  --enable-statistics   Compute statistics or check for unpack data loss
  --profile             Measure the number of calls and time spent in different methods
```

## Optimizing

For faster analysis, first extract all the necessary files, and then use the `--no-extract` and `--no-specialize` options

You should also try to exclude as many files as possible, either based on their mime-type:

```
--exclude-mime audio/* --exclude-mime image/* --exclude-mime video/*
```

... or based on their path:
```
--exclude */build/* --exclude *.txt --exclude *.json
```

If folders have been renamed (apart from the root file), try to rename them so they match. Otherwise, many files will have to be compared to attempt to detect the ones that have been moved.
