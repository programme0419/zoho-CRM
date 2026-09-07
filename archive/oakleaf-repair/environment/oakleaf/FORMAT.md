# Oakleaf v1 on-disk format

Oakleaf is a small embedded key-value store. This file is normative. The
Python tree under `/app/oakleaf` is a shipping snapshot that does **not**
implement every rule below correctly — existing production directories were
written by a spec-accurate engine and must keep opening.

## Directory

```
<db>/
  oak.manifest
  oak.wal
  sst/NNNNNN.sst      # 6-digit lowercase hex file id
```

All multi-byte integers are **little-endian**. Keys and values are raw bytes.
Keys are ordered by **unsigned memcmp** (the first differing byte is compared
as 0..255, not as a signed 8-bit value). Empty keys are illegal. Empty values
are legal and distinct from a delete.

## Sequence numbers

`uint64`, starting at 1, strictly increasing, **unsigned** compare. A higher
sequence always wins for a key, including values with the high bit set.

## WAL (`oak.wal`)

Header: `OAKW` + `u16` version=`1` + `u32` CRC-32 of those 6 bytes.

Record:

- `u32` payload_len
- payload: `u8` type | `u64` seq | `u16` key_len | key | `u32` val_len | val
- `u32` CRC-32 of (`payload_len` encoded as 4 bytes **concatenated with** payload)

Types: `1` PUT, `2` DEL, `3` FLUSH. DEL and FLUSH have empty values.

A mid-file CRC mismatch or truncated record is a torn write: keep every
complete record before it and ignore the tail. A bad header is fatal.

On recovery, ignore data records whose seq is `<=` the latest FLUSH seq.

## SSTable (`sst/NNNNNN.sst`)

- magic `OAKS`
- body: `u16` version=`1` + `u32` n_entries + entries
- `u32` CRC-32 of the body (everything after the magic)

Entry: `u8` flags | `u64` seq | `u16` klen | key | `u32` vlen | val.
`flags & 0x01` is a tombstone. Entries are sorted by (key ascending,
seq **descending**, unsigned).

## Manifest (`oak.manifest`)

- magic `OAKM`
- body: `u16` version=`1` + `u64` next_seq + `u32` n_files + `n_files * u32` file id
- `u32` CRC-32 of the body

File ids are listed oldest-first. `next_seq` is the next sequence to allocate
and is **never reset** by flush or compact.

## Operations

- `put key val` — allocate seq, WAL PUT, memtable PUT. An empty `val` is a
  live PUT of the empty byte string, **not** a delete.
- `delete key` — allocate seq, WAL DEL, memtable tombstone. Always written,
  even if the key is absent or only lives in an older SST.
- `get key` — the highest-seq entry for that key across memtable **and every
  SST**. A tombstone yields NOTFOUND. An empty live value yields the empty
  string, not NOTFOUND.
- `scan start end` — keys in `[start, end)` (start inclusive, **end exclusive**)
  in unsigned byte order. An empty `end` means +∞. Tombstoned keys are omitted.
- `flush` — write the memtable as a new newest SST, append its id, replace the
  WAL with a header plus a FLUSH record whose seq is the max seq just flushed.
- `compact` — collapse memtable + all SSTs to the newest entry per key,
  **drop** keys whose newest entry is a tombstone, replace the SST set with a
  single file id `1` (or none), preserve `next_seq`, reset the WAL with a
  FLUSH of `next_seq-1`.

Limits: key ≤ 65535 bytes, value ≤ 16 MiB. CRC is zlib/IEEE CRC-32.
