"""Cho phép `python -m src.aml ...`."""

from src.aml.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
