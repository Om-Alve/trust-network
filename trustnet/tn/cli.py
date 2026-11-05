"""trustnet.tn.cli module."""

import argparse


def main() -> None:
    """Display the command help."""
    parser = argparse.ArgumentParser(
        prog="tn", description="Manage trust network profiles and conversations."
    )
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":
    main()
