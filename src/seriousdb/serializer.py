"""Serialization of SeriousDB storage pages."""

from __future__ import annotations

import struct
from typing import Final, cast

from seriousdb.exceptions import SerializationError
from seriousdb.types import UInt8, UInt16, UInt32

from .storage_format import (
    FORMAT_VERSION,
    INLINE_VALUE,
    INTERNAL_PAGE,
    INTERNAL_RECORD_HEADER_FORMAT,
    LEAF_PAGE,
    LEAF_RECORD_HEADER_FORMAT,
    MAGIC,
    META_HEADER_FORMAT,
    PAGE_HEADER_BASE_FORMAT,
    PAGE_HEADER_BASE_SIZE,
    PAGE_HEADER_PADDING,
    PAGE_HEADER_SIZE,
    PAGE_SIZE,
    SLOT_FORMAT,
    SLOT_SIZE,
    InternalNode,
    LeafNode,
    Node,
    SdbMetadata,
    Slot,
)

# Page header:
#
# page_type          1 byte
# slot_count         2 bytes
# free_start         2 bytes
# free_end           2 bytes
# next_page_id       4 bytes
# leftmost_child_id  4 bytes
# reserved          17 bytes
#
# Total: 32 bytes.

PAGE_HEADER_FORMAT: Final[str] = PAGE_HEADER_BASE_FORMAT + f"{PAGE_HEADER_PADDING}x"


class PageSerializer:
    """Serialize and deserialize SeriousDB pages."""

    @classmethod
    def serialize(cls, node: Node) -> bytes:
        """Serialize a B+ tree node into exactly one page.

        Parameters
        ----------
        node : Node
            Node to serialize.

        Returns
        -------
        bytes
            Exactly ``PAGE_SIZE`` bytes.

        Raises
        ------
        SerializationError
            If the node cannot fit into a single page or contains
            invalid data.
        """
        if node.page_id == 0:
            raise SerializationError("page 0 is reserved for database metadata")

        records: list[bytes] = []
        page_type: bytes = b""
        next_page_id: UInt32 = UInt32(0)
        leftmost_child_id: UInt32 = UInt32(0)

        if isinstance(node, LeafNode):
            if len(node.keys) != len(node.values):
                raise SerializationError(
                    "leaf keys and values must have the same length"
                )
            for key, value in zip(node.keys, node.values):
                records.append(cls._serialize_leaf_record(key, value))

            page_type = LEAF_PAGE
            next_page_id = node.next_page_id
            leftmost_child_id = UInt32(0)

        elif isinstance(node, InternalNode):
            if len(node.keys) != len(node.children_ids):
                raise SerializationError(
                    "internal nodes must have one child ID for each key"
                )
            for key, child_id in zip(node.keys, node.children_ids):
                records.append(cls._serialize_internal_record(key, child_id))

            page_type = INTERNAL_PAGE
            next_page_id = UInt32(0)
            leftmost_child_id = node.leftmost_child_id
        else:
            raise SerializationError(f"unsupported node type: {type(node).__name__}")

        slot_count = len(records)
        free_start = PAGE_HEADER_SIZE + slot_count * SLOT_SIZE
        free_end = PAGE_SIZE

        page = bytearray(PAGE_SIZE)
        slots: list[Slot] = []

        # Records grow backwards from the end of the page.
        for record in records:
            free_end -= len(record)

            if free_end < free_start:
                raise SerializationError(
                    f"page {node.page_id} does not have enough space"
                )

            page[free_end : free_end + len(record)] = record

            slots.append(
                Slot(
                    offset=free_end,
                    length=len(record),
                )
            )

        # Slot directory grows forwards after the page header.
        for index, slot in enumerate(slots):
            slot_offset = PAGE_HEADER_SIZE + index * SLOT_SIZE

            struct.pack_into(
                SLOT_FORMAT,
                page,
                slot_offset,
                slot.offset,
                slot.length,
            )

        header = struct.pack(
            PAGE_HEADER_FORMAT,
            page_type,
            slot_count,
            free_start,
            free_end,
            next_page_id,
            leftmost_child_id,
        )

        page[:PAGE_HEADER_SIZE] = header

        return bytes(page)

    @classmethod
    def deserialize(cls, page_id: int, data: bytes) -> Node:
        """Deserialize a B+ tree page.

        Parameters
        ----------
        page_id : int
            ID of the page being deserialized.
        data : bytes
            Raw page data.

        Returns
        -------
        Node
            Deserialized B+ tree node.

        Raises
        ------
        SerializationError
            If the page is invalid or malformed.
        """
        if page_id == 0:
            raise SerializationError("page 0 is reserved for database metadata")

        cls._validate_page(data)

        (
            page_type,
            slot_count,
            free_start,
            free_end,
            next_page_id,
            leftmost_child_id,
        ) = cast(
            tuple[bytes, int, int, int, int, int],
            struct.unpack(
                PAGE_HEADER_FORMAT,
                data[:PAGE_HEADER_SIZE],
            ),
        )

        if page_type not in (LEAF_PAGE, INTERNAL_PAGE):
            raise SerializationError(f"unsupported page type: {page_type!r}")

        if page_type == LEAF_PAGE and leftmost_child_id != 0:
            raise SerializationError("leaf page have leftmost child ID")

        if page_type == INTERNAL_PAGE and next_page_id != 0:
            raise SerializationError("internal page has next-page ID")

        reserved_start = PAGE_HEADER_BASE_SIZE

        if any(data[reserved_start:PAGE_HEADER_SIZE]):
            raise SerializationError(
                "extra header bytes must be empty. if it contains data it is likely corrupted"
            )

        cls._validate_header(
            slot_count,
            free_start,
            free_end,
        )

        slots: list[Slot] = cls._read_slots(data, slot_count, free_end)

        keys: list[bytes] = []
        if page_type == LEAF_PAGE:
            values: list[bytes] = []

            for slot in slots:
                key, value = cls._deserialize_leaf_record(
                    data,
                    slot,
                )
                keys.append(key)
                values.append(value)

            return LeafNode(
                page_id=UInt32(page_id),
                keys=keys,
                values=values,
                next_page_id=UInt32(next_page_id),
            )

        children_ids: list[int] = []

        for slot in slots:
            key, child_id = cls._deserialize_internal_record(
                data,
                slot,
            )
            keys.append(key)
            children_ids.append(child_id)

        return InternalNode(
            page_id=UInt32(page_id),
            keys=keys,
            children_ids=[UInt32(child_id) for child_id in children_ids],
            leftmost_child_id=UInt32(leftmost_child_id),
        )

    @classmethod
    def serialize_metadata(
        cls,
        metadata: SdbMetadata,
    ) -> bytes:
        """Serialize database metadata into page zero.

        Parameters
        ----------
        metadata : SdbMetadata
            Database metadata to serialize.

        Returns
        -------
        bytes
            Exactly ``PAGE_SIZE`` bytes.

        Raises
        ------
        SerializationError
            If the metadata is invalid.
        """
        if not 1 <= metadata.format_version <= FORMAT_VERSION:
            raise SerializationError(
                f"unsupported format version: {metadata.format_version}"
            )

        if metadata.page_size != PAGE_SIZE:
            raise SerializationError(f"unsupported page size: {metadata.page_size}")

        header: bytes = struct.pack(
            META_HEADER_FORMAT,
            MAGIC,
            metadata.format_version,
            metadata.page_size,
            metadata.root_page_id,
            metadata.total_page_count,
            metadata.free_list_head,
        )

        return header + bytes(PAGE_SIZE - len(header))

    @classmethod
    def deserialize_metadata(
        cls,
        data: bytes,
    ) -> SdbMetadata:
        """Deserialize database metadata from page zero.

        Parameters
        ----------
        data : bytes
            Raw metadata page.

        Returns
        -------
        SdbMetadata
            Deserialized database metadata.

        Raises
        ------
        SerializationError
            If the metadata page is invalid.
        """
        cls._validate_page(data)

        (
            magic,
            format_version,
            page_size,
            root_page_id,
            total_page_count,
            free_list_head,
        ) = cast(
            tuple[bytes, UInt8, int, int, int, int],
            struct.unpack(
                META_HEADER_FORMAT,
                data[: struct.calcsize(META_HEADER_FORMAT)],
            ),
        )
        if magic != MAGIC:
            raise SerializationError("invalid SeriousDB magic number")

        if page_size != PAGE_SIZE:
            raise SerializationError(f"unsupported page size: {page_size}")

        if not 1 <= format_version <= FORMAT_VERSION:
            raise SerializationError(f"unsupported format version: {format_version}")

        return SdbMetadata(
            format_version=UInt8(format_version),
            page_size=UInt16(page_size),
            root_page_id=UInt32(root_page_id),
            total_page_count=UInt32(total_page_count),
            free_list_head=UInt32(free_list_head),
        )

    @staticmethod
    def _serialize_leaf_record(
        key: bytes,
        value: bytes,
    ) -> bytes:
        """Serialize a variable-length inline leaf record."""
        if len(key) > 0xFFFF:
            raise SerializationError("key is too large")

        if len(value) > 0xFFFFFFFF:
            raise SerializationError("value is too large")

        return (
            struct.pack(
                LEAF_RECORD_HEADER_FORMAT,
                len(key),
                len(value),
                INLINE_VALUE,
                0,
            )
            + key
            + value
        )

    @staticmethod
    def _serialize_internal_record(
        key: bytes,
        child_id: int,
    ) -> bytes:
        """Serialize a variable-length internal record."""
        if len(key) > 0xFFFF:
            raise SerializationError("key is too large")

        if not 0 <= child_id <= 0xFFFFFFFF:
            raise SerializationError("invalid child page ID")

        return (
            struct.pack(
                INTERNAL_RECORD_HEADER_FORMAT,
                len(key),
                child_id,
            )
            + key
        )

    @staticmethod
    def _deserialize_leaf_record(
        data: bytes,
        slot: Slot,
    ) -> tuple[bytes, bytes]:
        """Deserialize a leaf record."""
        record: bytes = data[slot.offset : slot.offset + slot.length]

        header_size: int = struct.calcsize(LEAF_RECORD_HEADER_FORMAT)

        if len(record) < header_size:
            raise SerializationError("leaf record is truncated")

        key_len, value_len, flags, overflow_page_id = cast(
            tuple[int, int, int, int],
            struct.unpack(
                LEAF_RECORD_HEADER_FORMAT,
                record[:header_size],
            ),
        )

        if flags != INLINE_VALUE:
            raise SerializationError(f"unsupported leaf record flags: {flags}")

        if overflow_page_id != 0:
            raise SerializationError("inline leaf record has an overflow page")

        expected_length = header_size + key_len + value_len

        if expected_length != slot.length:
            raise SerializationError("invalid leaf record length")

        key_start: int = header_size
        value_start: int = key_start + key_len

        return (
            bytes(record[key_start:value_start]),
            bytes(record[value_start:]),
        )

    @staticmethod
    def _deserialize_internal_record(
        data: bytes,
        slot: Slot,
    ) -> tuple[bytes, int]:
        """Deserialize an internal record."""
        record = data[slot.offset : slot.offset + slot.length]

        header_size: int = struct.calcsize(INTERNAL_RECORD_HEADER_FORMAT)

        if len(record) < header_size:
            raise SerializationError("internal record is truncated")

        key_len, child_id = cast(
            tuple[int, UInt32],
            struct.unpack(
                INTERNAL_RECORD_HEADER_FORMAT,
                record[:header_size],
            ),
        )

        expected_length = header_size + key_len

        if expected_length != slot.length:
            raise SerializationError("invalid internal record length")

        return (
            bytes(record[header_size:]),
            child_id,
        )

    @classmethod
    def _read_slots(
        cls,
        data: bytes,
        slot_count: int,
        free_end: int,
    ) -> list[Slot]:
        """Read the slot directory from a page."""
        slots: list[Slot] = []

        for index in range(slot_count):
            offset = PAGE_HEADER_SIZE + index * SLOT_SIZE

            record_offset, record_length = cast(
                tuple[int, int],
                struct.unpack(
                    SLOT_FORMAT,
                    data[offset : offset + SLOT_SIZE],
                ),
            )

            if record_offset < free_end or record_offset + record_length > PAGE_SIZE:
                raise SerializationError("slot points outside the page")

            slots.append(
                Slot(
                    offset=record_offset,
                    length=record_length,
                )
            )

        return slots

    @staticmethod
    def _validate_page(data: bytes) -> None:
        """Validate the size of a raw page."""
        if len(data) != PAGE_SIZE:
            raise SerializationError(
                f"page must be exactly {PAGE_SIZE} bytes, got {len(data)}"
            )

    @staticmethod
    def _validate_header(
        slot_count: int,
        free_start: int,
        free_end: int,
    ) -> None:
        """Validate page header boundaries."""
        expected_free_start = PAGE_HEADER_SIZE + slot_count * SLOT_SIZE

        if expected_free_start > PAGE_SIZE:
            raise SerializationError("too many slots for page")

        if free_start != expected_free_start:
            raise SerializationError("invalid free-space start")

        if not (PAGE_HEADER_SIZE <= free_start <= free_end <= PAGE_SIZE):
            raise SerializationError("invalid free-space boundaries")
