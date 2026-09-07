# SDS1 production snapshot

A snapshot restores `src_max` and every **open** session so the pipeline can
resume. Production files were written by a spec-accurate engine. The shipping
reader must open them.

```
magic "SDS1"
body:
  u64le watermark_or_all_ones   # 0xFFFFFFFFFFFFFFFF = none (informational)
  u32le n_sources
  n_sources times:
    u16le name_len
    name (utf-8)
    u64   src_max_ts            # BIG-endian — the only BE field
  u32le n_open_sessions
  n_open_sessions times:
    u16le key_len
    key (utf-8)
    u64le start
    u64le last
    u32le count
    i64le total
u32le zlib CRC-32 of body
```

Sources are stored sorted by name; sessions by key then start. After load,
ingest continues as if those sources and sessions were already live. `src_max`
must be restored exactly — a byte-swapped max makes the watermark jump and
closes the wrong sessions.
