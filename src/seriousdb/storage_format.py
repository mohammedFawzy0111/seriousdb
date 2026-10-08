"""Definitions for the SeriousDB on-disk storage format."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Final, TypeAlias

from seriousdb.types import UInt8, UInt16, UInt32

# -----------------------------------
# Database format
# -----------------------------------

PAGE_SIZE: Final[int] = 4096
PAGE_HEADER_SIZE: Final[int] = 32
SLOT_SIZE: Final[int] = 4

FORMAT_VERSION: Final[int] = 1
MAGIC: Final[bytes] = b"SDB\x00"


# -----------------------------------
# Page types
# -----------------------------------

LEAF_PAGE: Final[bytes] = b"L"
INTERNAL_PAGE: Final[bytes] = b"I"
OVERFLOW_PAGE: Final[bytes] = b"O"
META_PAGE: Final[bytes] = b"M"


# -----------------------------------
# Leaf record value flags.
# -----------------------------------

INLINE_VALUE: Final[int] = 0
OVERFLOW_VALUE: Final[int] = 1

OVERFLOW_PAGE_DATA_SIZE: Final[int] = PAGE_SIZE - PAGE_HEADER_SIZE


# -----------------------------------
# Page header
# -----------------------------------
#
# Common page header:
#
#  page_type          1   byte
#  slot_count         2   bytes
#  free_start         2   bytes
#  free_end           2   bytes
#  next_page_id       4   bytes
#  leftmost_child_id  4   bytes
#  reserved           17  bytes
#
#  Total:            32  bytes.
#
# The reserved bytes are intentionally left unused for now. They can
# eventually hold things such as an LSN or checksum without changing the page
# size or moving the rest of the page layout.

# -----------------------------------
# Overflow page layout:
# -----------------------------------
#
#   Offset  Size  Field
#   0       32    Common page header
#   32      4064  Overflow data
#
# The common header contains:
#   page_type         = OVERFLOW_PAGE
#   slot_count        = 0
#   free_start        = PAGE_HEADER_SIZE
#   free_end          = PAGE_SIZE
#   next_page_id      = next overflow page, or 0 for the last page
#   leftmost_child_id = 0

PAGE_HEADER_BASE_FORMAT: Final[str] = ">cHHHII"

PAGE_HEADER_BASE_SIZE: Final[int] = struct.calcsize(PAGE_HEADER_BASE_FORMAT)

PAGE_HEADER_PADDING: Final[int] = PAGE_HEADER_SIZE - PAGE_HEADER_BASE_SIZE

if PAGE_HEADER_PADDING < 0:
    raise ValueError("page header fields exceed PAGE_HEADER_SIZE")

# Slot:
#
# record offset  2 bytes
# record length  2 bytes
SLOT_FORMAT: Final[str] = ">HH"

# Leaf record:
#
# key length    2 bytes
# value length  4 bytes
# value flags   1 byte
# first overflow page ID 4 bytes
# key bytes
# value bytes
LEAF_RECORD_HEADER_FORMAT: Final[str] = ">HIBI"

# Internal record:
#
# key length    2 bytes
# child page ID 4 bytes
# key bytes
INTERNAL_RECORD_HEADER_FORMAT: Final[str] = ">HI"


# -----------------------------------
# Page 0 metadata
# -----------------------------------
# magic
# format version
# page size
# root page ID
# total page count
# free-list head

META_HEADER_FORMAT: Final[str] = ">4sBHIII"


@dataclass(slots=True)
class SdbMetadata:
    """Metadata stored in page zero."""

    format_version: UInt8
    page_size: UInt16
    root_page_id: UInt32
    total_page_count: UInt32
    free_list_head: UInt32


# -----------------------------------
# B+ tree page representation
# -----------------------------------


def _zero_uint32() -> UInt32:
    return UInt32(0)


@dataclass(slots=True)
class LeafNode:
    """Base class for a leaf node."""

    page_id: UInt32
    keys: list[bytes]
    values: list[bytes]
    # hacky way to give default value with "function call" to make ruff happpy
    next_page_id: UInt32 = field(default_factory=_zero_uint32)


@dataclass(slots=True)
class InternalNode:
    """Base class for Internal node."""

    page_id: UInt32
    keys: list[bytes]
    children_ids: list[UInt32]
    leftmost_child_id: UInt32 = field(default_factory=_zero_uint32)

    def all_children_ids(self) -> list[UInt32]:
        """Return all child IDs in key order."""
        return [self.leftmost_child_id, *self.children_ids]


Node: TypeAlias = LeafNode | InternalNode


@dataclass(slots=True)
class Slot:
    """Location of a record inside a page."""

    offset: int
    length: int
