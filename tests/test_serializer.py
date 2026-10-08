import struct

import pytest

from seriousdb.exceptions import SerializationError
from seriousdb.serializer import PageSerializer
from seriousdb.storage_format import (
    FORMAT_VERSION,
    INTERNAL_PAGE,
    LEAF_PAGE,
    LEAF_RECORD_HEADER_FORMAT,
    META_HEADER_FORMAT,
    PAGE_HEADER_BASE_FORMAT,
    PAGE_HEADER_SIZE,
    PAGE_SIZE,
    SLOT_FORMAT,
    SLOT_SIZE,
    InternalNode,
    LeafNode,
    SdbMetadata,
)
from seriousdb.types import UInt8, UInt16, UInt32


class TestPageSerializer:
    def test_leaf_round_trip(self) -> None:
        node = LeafNode(
            page_id=UInt32(1),
            keys=[b"foo", b"bar"],
            values=[b"Alice", b"Bob"],
        )

        data = PageSerializer.serialize(node)
        result = PageSerializer.deserialize(UInt32(1), data)

        assert result == node

    def test_internal_round_trip(self) -> None:
        node = InternalNode(
            page_id=UInt32(2),
            keys=[b"foo", b"bar"],
            children_ids=[UInt32(3), UInt32(4)],
            leftmost_child_id=UInt32(5),
        )

        data = PageSerializer.serialize(node)
        result = PageSerializer.deserialize(UInt32(2), data)

        assert result == node

    def test_empty_leaf_round_trip(self) -> None:
        node = LeafNode(
            page_id=UInt32(1),
            keys=[],
            values=[],
        )

        data = PageSerializer.serialize(node)
        result = PageSerializer.deserialize(UInt32(1), data)

        assert result == node

    def test_empty_internal_round_trip(self) -> None:
        node = InternalNode(
            page_id=UInt32(1),
            keys=[],
            children_ids=[],
        )

        data = PageSerializer.serialize(node)
        result = PageSerializer.deserialize(UInt32(1), data)

        assert result == node

    def test_serialized_page_has_correct_size(self) -> None:
        node = LeafNode(
            page_id=UInt32(1),
            keys=[b"key"],
            values=[b"value"],
        )

        data = PageSerializer.serialize(node)

        assert len(data) == PAGE_SIZE

    def test_page_zero_cannot_be_serialized(self) -> None:
        node = LeafNode(
            page_id=UInt32(0),
            keys=[],
            values=[],
        )

        with pytest.raises(SerializationError):
            PageSerializer.serialize(node)

    def test_page_zero_cannot_be_deserialized(self) -> None:
        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(0), bytes(PAGE_SIZE))

    def test_page_smaller_than_page_size_is_rejected(self) -> None:
        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(1), bytes(PAGE_SIZE - 1))

    def test_page_larger_than_page_size_is_rejected(self) -> None:
        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(1), bytes(PAGE_SIZE + 1))

    def test_leaf_rejects_mismatched_keys_and_values(self) -> None:
        node = LeafNode(
            page_id=UInt32(1),
            keys=[b"key"],
            values=[],
        )

        with pytest.raises(SerializationError):
            PageSerializer.serialize(node)

    def test_invalid_page_type_is_rejected(self) -> None:
        data = bytearray(PAGE_SIZE)
        data[0] = ord("X")

        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(1), bytes(data))

    def test_leaf_with_leftmost_child_id_is_rejected(self) -> None:
        data = bytearray(PAGE_SIZE)

        struct.pack_into(
            PAGE_HEADER_BASE_FORMAT,
            data,
            0,
            LEAF_PAGE,
            0,
            PAGE_HEADER_SIZE,
            PAGE_SIZE,
            0,
            123,
        )

        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(1), bytes(data))

    def test_internal_with_next_page_id_is_rejected(self) -> None:
        data = bytearray(PAGE_SIZE)

        struct.pack_into(
            PAGE_HEADER_BASE_FORMAT,
            data,
            0,
            INTERNAL_PAGE,
            0,
            PAGE_HEADER_SIZE,
            PAGE_SIZE,
            123,
            0,
        )

        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(1), bytes(data))

    def test_non_zero_reserved_header_bytes_are_rejected(self) -> None:
        node = LeafNode(
            page_id=UInt32(1),
            keys=[],
            values=[],
        )

        data = bytearray(PageSerializer.serialize(node))

        base_header_size = struct.calcsize(PAGE_HEADER_BASE_FORMAT)
        data[base_header_size] = 1

        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(1), bytes(data))

    def test_leaf_next_page_id_round_trip(self) -> None:
        node = LeafNode(
            page_id=UInt32(1),
            keys=[b"a"],
            values=[b"b"],
            next_page_id=UInt32(7),
        )

        data = PageSerializer.serialize(node)
        assert PageSerializer.deserialize(UInt32(1), data) == node

    def test_slot_pointing_into_slot_dirctory_is_rejected(self) -> None:
        node = LeafNode(
            page_id=UInt32(1),
            keys=[b"k"],
            values=[b"v"],
        )

        data = bytearray(PageSerializer.serialize(node))
        # make slot points inside the wrong position (in the slot dirctory)
        struct.pack_into(SLOT_FORMAT, data, PAGE_HEADER_SIZE, PAGE_HEADER_SIZE, 8)
        with pytest.raises(SerializationError):
            PageSerializer.deserialize(UInt32(1), bytes(data))

    def test_exactly_full_page_round_trips(self) -> None:
        overhead = (
            PAGE_HEADER_SIZE + SLOT_SIZE + struct.calcsize(LEAF_RECORD_HEADER_FORMAT)
        )
        node = LeafNode(
            page_id=UInt32(1),
            keys=[b"k"],
            values=[b"v" * (PAGE_SIZE - overhead - 1)],
        )
        data = PageSerializer.serialize(node)
        assert PageSerializer.deserialize(UInt32(1), data) == node

    def test_one_byte_too_large_is_rejected(self) -> None:
        overhead = (
            PAGE_HEADER_SIZE + SLOT_SIZE + struct.calcsize(LEAF_RECORD_HEADER_FORMAT)
        )
        node = LeafNode(
            page_id=UInt32(1),
            keys=[b"k"],
            values=[b"v" * (PAGE_SIZE - overhead)],
        )
        with pytest.raises(SerializationError):
            PageSerializer.serialize(node)

    def test_internal_rejects_mismatched_keys_and_children(self) -> None:
        node = InternalNode(page_id=UInt32(1), keys=[b"k"], children_ids=[])
        with pytest.raises(SerializationError):
            PageSerializer.serialize(node)


class TestMetadataSerializer:
    def make_metadata(self) -> SdbMetadata:
        return SdbMetadata(
            format_version=UInt8(FORMAT_VERSION),
            page_size=UInt16(PAGE_SIZE),
            root_page_id=UInt32(1),
            total_page_count=UInt32(10),
            free_list_head=UInt32(0),
        )

    def test_round_trip(self) -> None:
        metadata = self.make_metadata()

        data = PageSerializer.serialize_metadata(metadata)
        result = PageSerializer.deserialize_metadata(data)

        assert result == metadata

    def test_serialized_metadata_has_correct_size(self) -> None:
        metadata = self.make_metadata()

        data = PageSerializer.serialize_metadata(metadata)

        assert len(data) == PAGE_SIZE

    def test_invalid_magic_is_rejected(self) -> None:
        metadata = self.make_metadata()
        data = bytearray(PageSerializer.serialize_metadata(metadata))

        data[0] ^= 0xFF

        with pytest.raises(SerializationError):
            PageSerializer.deserialize_metadata(bytes(data))

    def test_invalid_page_size_is_rejected(self) -> None:
        metadata = self.make_metadata()
        data = bytearray(PageSerializer.serialize_metadata(metadata))

        # Locate the page-size field from the actual metadata format.
        fields = list(
            struct.unpack(
                META_HEADER_FORMAT,
                data[: struct.calcsize(META_HEADER_FORMAT)],
            )
        )

        # magic, version, page_size, ...
        fields[2] = PAGE_SIZE + 1

        data[: struct.calcsize(META_HEADER_FORMAT)] = struct.pack(
            META_HEADER_FORMAT,
            *fields,
        )

        with pytest.raises(SerializationError):
            PageSerializer.deserialize_metadata(bytes(data))

    def test_unsupported_future_version_is_rejected(self) -> None:
        metadata = self.make_metadata()
        data = bytearray(PageSerializer.serialize_metadata(metadata))

        fields = list(
            struct.unpack(
                META_HEADER_FORMAT,
                data[: struct.calcsize(META_HEADER_FORMAT)],
            )
        )

        fields[1] = FORMAT_VERSION + 1

        data[: struct.calcsize(META_HEADER_FORMAT)] = struct.pack(
            META_HEADER_FORMAT,
            *fields,
        )

        with pytest.raises(SerializationError):
            PageSerializer.deserialize_metadata(bytes(data))

    def test_zero_version_is_rejected(self) -> None:
        metadata = self.make_metadata()
        data = bytearray(PageSerializer.serialize_metadata(metadata))

        fields = list(
            struct.unpack(
                META_HEADER_FORMAT,
                data[: struct.calcsize(META_HEADER_FORMAT)],
            )
        )

        fields[1] = 0

        data[: struct.calcsize(META_HEADER_FORMAT)] = struct.pack(
            META_HEADER_FORMAT,
            *fields,
        )

        with pytest.raises(SerializationError):
            PageSerializer.deserialize_metadata(bytes(data))

    def test_metadata_page_size_must_match_storage_page_size(self) -> None:
        metadata = self.make_metadata()
        data = bytearray(PageSerializer.serialize_metadata(metadata))

        fields = list(
            struct.unpack(
                META_HEADER_FORMAT,
                data[: struct.calcsize(META_HEADER_FORMAT)],
            )
        )

        fields[2] = 1024

        data[: struct.calcsize(META_HEADER_FORMAT)] = struct.pack(
            META_HEADER_FORMAT,
            *fields,
        )

        with pytest.raises(SerializationError):
            PageSerializer.deserialize_metadata(bytes(data))
