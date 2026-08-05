"""Run the local JSON adapter with ``python -m src.relay_form_ocr``."""

from .cli import main


if __name__ == "__main__":
    import os
    try:
        from .cli import main
        code = main()
    except Exception:
        code = 1

    try:
        import psutil
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except Exception:
                pass
    except Exception:
        pass

    os._exit(code)
