from __future__ import annotations

import logging
import warnings

from rich.logging import RichHandler


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("trafilatura").setLevel(logging.WARNING)
    logging.getLogger("feedparser").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message="tzname .* identified but not understood")
    warnings.filterwarnings("ignore", message="discarding data")
