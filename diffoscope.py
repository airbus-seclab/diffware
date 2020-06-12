import sys
import argparse


def parse_diff(file_path):
    with open(file_path, "r") as f:
        content = f.read()
        print(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wrapper to run diffoscope on the output of difftool")
    parser.add_argument("difftool_args", nargs="*")
    parser.add_argument("FILE_PATH", type=str, help="Path to file created by running difftool")

    # We only parse the second argument (the first being the name of the script)
    # since the other will be used for diffoscope
    args = parser.parse_args([sys.argv[1]])

    parse_diff(args.FILE_PATH)
