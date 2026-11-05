"""trustnet.gate.__main__ module."""

import argparse


def main() -> None:
    """Display the command help."""
    parser = argparse.ArgumentParser(
        prog="python -m trustnet.gate", description="Run a trust network gate."
    )
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":
    main()
