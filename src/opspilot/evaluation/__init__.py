"""Evaluation concerns that cross a process boundary: the kept-run document and its store.

The evaluation runner lives outside the application and writes here; the application only reads.
The shapes live in the package the image ships because both sides have to agree on them, exactly
as both already agree on the configuration module.
"""
