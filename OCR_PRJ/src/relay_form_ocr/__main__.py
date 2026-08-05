"""Run the local JSON adapter with ``python -m src.relay_form_ocr``."""

from .cli import main


if __name__ == "__main__":
    import os
    os._exit(main())
