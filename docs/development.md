# Development guide

## Requirements

- Python 3.11 or newer
- `uv`

## Setup

```bash
uv sync
uv run pre-commit install
```

To sync development dependencies run following command:

```bash
uv sync --group dev
```

## Try it out

Open a Python shell with the project's dependencies available:

```bash
uv run python
```

```python
import seriousdb

seriousdb.set("name", "Alice")
seriousdb.get("name")
```

## Formatting

### Format Python files with `ruff`:

```bash
uv run ruff format .
```

### To check formatting without changing files:

```bash
uv run ruff format --check .
```

## Linting

### Lint python files with `ruff`:

```bash
uv run ruff check .
```

### Type checking with `ty`

```bash
uv run ty check .
```

### To fix linter errors and warning if possible run following command:

```bash
uv run ruff check --fix .
```

## Docstrings

Python docstrings follow the [NumPy style](https://numpydoc.readthedocs.io/en/latest/format.html).

Docstrings are required for public functions, classes and modules only; for private ones (prefixed
with `_`) they are optional. This is enforced by `ruff` (see [Linting](#linting)).

A docstring starts with a one-line summary, followed by the sections that apply, such as
`Parameters`, `Returns` and `Raises`:

```python
def select(self, key: str) -> str:
    """Return the value stored under `key`.

    Parameters
    ----------
    key : str
        Key to look up.

    Returns
    -------
    str
        The value stored under `key`.

    Raises
    ------
    ResourceNotFoundError
        If `key` does not exist.
    ServiceUnavailableError
        If no database has been loaded.
    """
```

See [`cache.py`](../src/seriousdb/cache.py) and [`api.py`](../src/seriousdb/api.py) for more
examples.

## Documentation

The docstrings above are the source for a generated, docstring-level API reference committed at
[`docs/reference/`](reference/index.md).
built with [Sphinx](https://www.sphinx-doc.org/) and
[sphinx-markdown-builder](https://pypi.org/project/sphinx-markdown-builder/) so it renders as plain
Markdown on GitHub — no hosted docs site required.

`docs/reference/` is committed, not gitignored, so it's readable straight from the repo. Don't edit
files under it by hand: edit the docstring instead and regenerate.

### Regenerate

```bash
uv sync --group docs
uv run --group docs python scripts/docs-reference.py
```

Commit any resulting changes under `docs/reference/` along with your docstring change. CI (see
[`.github/workflows/docs.yml`](../.github/workflows/docs.yml)) rebuilds it and fails the check if
the committed output doesn't match, so a stale reference is caught before merge.

### Adding a module

`docs/_sphinx/index.rst` lists the modules that get a generated page, currently `seriousdb.api` and
`seriousdb.exceptions` — the two modules [architecture.md](architecture.md) calls out as public. To
add another, add its dotted path to the `autosummary` list in that file and regenerate; the page
layout itself comes from the template at
[`docs/_sphinx/_templates/autosummary/module.rst`](_sphinx/_templates/autosummary/module.rst).
