from __future__ import annotations

from pathlib import Path


def select_directory(initial: str | Path) -> Path | None:
    """Show a native folder chooser and return its selected directory."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:  # pragma: no cover - depends on the desktop Python build
        raise RuntimeError("Native folder selection is unavailable on this installation.") from exc

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=str(Path(initial).expanduser()),
            title="Choose an XAS data folder",
            mustexist=True,
        )
        return Path(selected).resolve() if selected else None
    except tk.TclError as exc:
        raise RuntimeError(
            "The native folder window could not be opened. Enter the folder path in Session setup instead."
        ) from exc
    finally:
        if root is not None:
            root.destroy()
