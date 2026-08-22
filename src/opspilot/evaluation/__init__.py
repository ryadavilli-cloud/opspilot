"""What the offline evaluation owns inside the package the image ships.

Two things, for two different reasons. The judge's model construction, which nothing in a live
investigation imports. And the kept-run document and its store, which cross a process boundary:
the evaluation runner writes a kept run and the application only reads it, so both sides have to
agree on the shape, exactly as both already agree on the configuration module.
"""
