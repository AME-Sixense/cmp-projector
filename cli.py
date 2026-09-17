import argparse
import sys
import os
from core import __version__
from core.pipeline import run_project
import yaml

'''
File: cli.py
Author: Aaron Meyer
Date: 2024-09-19

Description: Thin CLI wrapper around core.pipeline.run_project() — the actual
pipeline logic (parse, offset/rotate, reproject, export) lives there so it can
be imported and called directly (by tests, other scripts, etc.) without going
through this script.
'''

if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Project a CMP survey to lat/long and export it.")
    arg_parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    arg_parser.add_argument("project", help="Project ID (project-id), as defined in config.yaml")
    arg_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print per-file detail for every skipped file, not just summary counts."
    )
    arg_parser.add_argument(
        "--outputs", metavar="LIST",
        help="Comma-separated exporter names to run instead of config.yaml's 'outputs' list "
             "for this run only, e.g. --outputs kmz,csv"
    )
    arg_parser.add_argument(
        "--groups", metavar="LIST",
        help="Comma-separated group names to include in the static_map output (default: all "
             "groups). Has no effect on any other output. e.g. --groups 1,3"
    )
    args = arg_parser.parse_args()
    outputs_override = args.outputs.split(",") if args.outputs else None
    group_filter = None
    if args.groups and args.groups.strip().lower() != "all":
        group_filter = [g.strip() for g in args.groups.split(",") if g.strip()]
        if not group_filter:
            arg_parser.error("--groups must list at least one group name, or be omitted/'all' for every group")

    try:
        with open('config.yaml', 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        run_project(args.project, config, verbose=args.verbose, outputs_override=outputs_override, group_filter=group_filter)

    except Exception as e:

        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        sys.stdout.write(f"\n   Error initiating the script. Exiting program.\n   ERROR:{e}\n   TYPE: {exc_type}\n   FILE: {fname} \n   LINE {exc_tb.tb_lineno}\n")
        sys.stdout.flush()
        sys.exit(0)
