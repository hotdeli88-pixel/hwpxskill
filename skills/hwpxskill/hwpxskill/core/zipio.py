"""원본 보존 ZIP 입출력.

kordoc zip-patch 방식: 바뀌지 않은 엔트리는 로컬 헤더·압축 데이터를 바이트 그대로 복사하고,
바뀐 엔트리만 같은 압축 방식으로 다시 압축한다. 엔트리 순서도 원본 그대로라
`mimetype`이 첫 번째·무압축이라는 HWPX 규칙이 저절로 지켜진다.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from ..errors import HwpxError

_SIG_LOCAL = 0x04034B50
_SIG_CENTRAL = 0x02014B50
_SIG_EOCD = 0x06054B50
_SIG_DESC = 0x08074B50
_DOS_EPOCH = (0 << 11, (1 << 5) | 1)  # 1980-01-01 00:00 (한컴 저장본과 같은 값)


@dataclass
class ZipEntry:
    name: str
    raw_name: bytes
    version_made: int
    version_needed: int
    flags: int
    method: int
    mtime: int
    mdate: int
    crc: int
    csize: int
    usize: int
    central_extra: bytes
    comment: bytes
    disk: int
    iattr: int
    eattr: int
    offset: int
    local_extra: bytes = b""
    data_start: int = 0
    record_end: int = 0  # 로컬 레코드(헤더+데이터+데이터 설명자) 끝


@dataclass
class ZipArchive:
    data: bytes
    entries: List[ZipEntry] = field(default_factory=list)
    comment: bytes = b""

    @classmethod
    def from_bytes(cls, data: bytes) -> "ZipArchive":
        arc = cls(data)
        arc._parse()
        return arc

    @classmethod
    def from_file(cls, path: str) -> "ZipArchive":
        with open(path, "rb") as f:
            return cls.from_bytes(f.read())

    # ── 읽기 ──
    def _parse(self) -> None:
        d = self.data
        eocd = d.rfind(struct.pack("<I", _SIG_EOCD), max(0, len(d) - 65557))
        if eocd < 0:
            raise HwpxError("ZIP 형식이 아닙니다 (HWPX가 아니거나 손상된 파일)")
        (_, disk_no, cd_disk, n_disk, n_total, cd_size, cd_off, clen) = struct.unpack_from("<IHHHHIIH", d, eocd)
        if n_total == 0xFFFF or cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
            raise HwpxError("ZIP64 형식은 지원하지 않습니다")
        self.comment = d[eocd + 22:eocd + 22 + clen]
        pos = cd_off
        for _ in range(n_total):
            if struct.unpack_from("<I", d, pos)[0] != _SIG_CENTRAL:
                raise HwpxError("ZIP 중앙 디렉터리가 손상되었습니다")
            (_, vmade, vneed, flags, method, mtime, mdate, crc, csize, usize,
             nlen, mlen, klen, disk, iattr, eattr, off) = struct.unpack_from("<IHHHHHHIIIHHHHHII", d, pos)
            raw_name = d[pos + 46:pos + 46 + nlen]
            extra = d[pos + 46 + nlen:pos + 46 + nlen + mlen]
            comment = d[pos + 46 + nlen + mlen:pos + 46 + nlen + mlen + klen]
            name = raw_name.decode("utf-8" if flags & 0x800 else "cp437", errors="replace")
            if flags & 0x800 == 0:
                try:
                    name = raw_name.decode("utf-8")
                except UnicodeDecodeError:
                    pass
            e = ZipEntry(name, raw_name, vmade, vneed, flags, method, mtime, mdate, crc, csize, usize,
                         extra, comment, disk, iattr, eattr, off)
            self._read_local(e)
            self.entries.append(e)
            pos += 46 + nlen + mlen + klen

    def _read_local(self, e: ZipEntry) -> None:
        d = self.data
        if struct.unpack_from("<I", d, e.offset)[0] != _SIG_LOCAL:
            raise HwpxError(f"ZIP 로컬 헤더가 손상되었습니다: {e.name}")
        nlen, mlen = struct.unpack_from("<HH", d, e.offset + 26)
        e.local_extra = d[e.offset + 30 + nlen:e.offset + 30 + nlen + mlen]
        e.data_start = e.offset + 30 + nlen + mlen
        end = e.data_start + e.csize
        if e.flags & 0x08:
            if struct.unpack_from("<I", d, end)[0] == _SIG_DESC:
                end += 16
            else:
                end += 12
        e.record_end = end

    def names(self) -> List[str]:
        return [e.name for e in self.entries]

    def get(self, name: str) -> Optional[ZipEntry]:
        for e in self.entries:
            if e.name == name:
                return e
        return None

    def read(self, name: str) -> bytes:
        e = self.get(name)
        if e is None:
            raise KeyError(name)
        if e.flags & 0x01:
            raise HwpxError("암호화된(배포용) 문서는 편집할 수 없습니다. 한글에서 암호를 해제해 주세요")
        raw = self.data[e.data_start:e.data_start + e.csize]
        if e.method == 0:
            return raw
        if e.method == 8:
            return zlib.decompress(raw, -15)
        raise HwpxError(f"지원하지 않는 압축 방식({e.method}): {e.name}")

    # ── 쓰기 ──
    def rebuild(self, replaced: Dict[str, bytes], added: Iterable[Tuple[str, bytes, bool]] = (),
                removed: Iterable[str] = ()) -> bytes:
        """바뀐 엔트리만 다시 압축한 새 ZIP 바이트. added = (이름, 데이터, 압축여부)."""
        removed_set = set(removed)
        out = bytearray()
        new_offsets: Dict[int, int] = {}
        patched: Dict[int, Tuple[int, int, int, int]] = {}  # id(entry) -> flags, crc, csize, usize
        for e in sorted(self.entries, key=lambda x: x.offset):
            if e.name in removed_set:
                continue
            new_offsets[id(e)] = len(out)
            if e.name not in replaced:
                out += self.data[e.offset:e.record_end]
                continue
            payload = replaced[e.name]
            comp = _compress(payload, e.method)
            crc = zlib.crc32(payload) & 0xFFFFFFFF
            flags = e.flags & ~0x08
            out += struct.pack("<IHHHHHIIIHH", _SIG_LOCAL, e.version_needed, flags, e.method,
                               e.mtime, e.mdate, crc, len(comp), len(payload), len(e.raw_name),
                               len(e.local_extra))
            out += e.raw_name + e.local_extra + comp
            patched[id(e)] = (flags, crc, len(comp), len(payload))

        extra_entries: List[ZipEntry] = []
        for name, payload, compress in added:
            method = 8 if compress else 0
            comp = _compress(payload, method)
            if method == 8 and len(comp) >= len(payload):
                method, comp = 0, payload
            raw_name = name.encode("utf-8")
            flags = 0x800 if any(ord(c) > 127 for c in name) else 0
            crc = zlib.crc32(payload) & 0xFFFFFFFF
            e = ZipEntry(name, raw_name, 20, 20, flags, method, _DOS_EPOCH[0], _DOS_EPOCH[1], crc,
                         len(comp), len(payload), b"", b"", 0, 0, 0, len(out))
            out += struct.pack("<IHHHHHIIIHH", _SIG_LOCAL, 20, flags, method, e.mtime, e.mdate, crc,
                               len(comp), len(payload), len(raw_name), 0)
            out += raw_name + comp
            new_offsets[id(e)] = e.offset
            extra_entries.append(e)

        cd_start = len(out)
        count = 0
        for e in self.entries + extra_entries:
            if e.name in removed_set:
                continue
            flags, crc, csize, usize = patched.get(id(e), (e.flags, e.crc, e.csize, e.usize))
            out += struct.pack("<IHHHHHHIIIHHHHHII", _SIG_CENTRAL, e.version_made, e.version_needed, flags,
                               e.method, e.mtime, e.mdate, crc, csize, usize, len(e.raw_name),
                               len(e.central_extra), len(e.comment), e.disk, e.iattr, e.eattr,
                               new_offsets[id(e)])
            out += e.raw_name + e.central_extra + e.comment
            count += 1
        cd_size = len(out) - cd_start
        out += struct.pack("<IHHHHIIH", _SIG_EOCD, 0, 0, count, count, cd_size, cd_start, len(self.comment))
        out += self.comment
        return bytes(out)


def _compress(payload: bytes, method: int) -> bytes:
    if method == 0:
        return payload
    if method == 8:
        c = zlib.compressobj(6, zlib.DEFLATED, -15)
        return c.compress(payload) + c.flush()
    raise HwpxError(f"지원하지 않는 압축 방식({method})")


def build_zip(files: List[Tuple[str, bytes, bool]]) -> bytes:
    """새 ZIP을 만든다 (새 문서 생성용). 첫 파일은 mimetype(무압축)이어야 한다."""
    if not files or files[0][0] != "mimetype":
        raise HwpxError("새 HWPX의 첫 파일은 mimetype 이어야 합니다")
    empty = ZipArchive(b"")
    return empty.rebuild({}, files)
