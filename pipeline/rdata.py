"""Minimal reader for R .RData files (XDR serialization v2/v3) -> pandas DataFrames.
Only supports what the Lahman package uses: pairlists, lists, vectors, factors, data.frames."""
import struct, lzma, gzip, bz2
import pandas as pd

NA_INT = -2147483648

class _R:
    def __init__(s, b): s.b, s.p, s.refs = b, 0, []
    def i32(s):
        v = struct.unpack_from('>i', s.b, s.p)[0]; s.p += 4; return v
    def f64s(s, n):
        v = struct.unpack_from('>%dd' % n, s.b, s.p); s.p += 8 * n; return list(v)
    def i32s(s, n):
        v = struct.unpack_from('>%di' % n, s.b, s.p); s.p += 4 * n; return list(v)
    def length(s):
        n = s.i32()
        if n == -1:
            hi, lo = s.i32(), s.i32(); n = (hi << 32) + lo
        return n
    def item(s):
        flags = s.i32(); t = flags & 255
        has_attr = bool(flags & 512); has_tag = bool(flags & 1024); is_obj = bool(flags & 256)
        if t == 254: return None            # NILVALUE
        if t == 242 or t == 253 or t == 251 or t == 252 or t == 250: return None  # EMPTYENV, GLOBALENV etc.
        if t == 255:                        # REFSXP
            idx = flags >> 8
            if idx == 0: idx = s.i32()
            return s.refs[idx - 1]
        if t == 1:                          # SYMSXP
            name = s.item(); s.refs.append(name); return name
        if t == 9:                          # CHARSXP
            n = s.i32()
            if n == -1: return None
            v = s.b[s.p:s.p + n].decode('utf-8', 'replace'); s.p += n; return v
        if t in (2, 6):                     # LISTSXP / LANGSXP
            attr = s.item() if has_attr else None
            tag = s.item() if has_tag else None
            car = s.item(); cdr = s.item()
            lst = [(tag, car)] + (cdr if isinstance(cdr, list) else [])
            return lst
        if t == 238: raise NotImplementedError('ALTREP')
        # vectors
        if t == 16:
            n = s.length(); out = [s.item() for _ in range(n)]
        elif t == 13 or t == 10:
            n = s.length(); out = s.i32s(n)
            out = [None if v == NA_INT else v for v in out]
        elif t == 14:
            n = s.length(); out = s.f64s(n)
            out = [None if v != v else v for v in out]
        elif t in (19, 20):
            n = s.length(); out = [s.item() for _ in range(n)]
        elif t == 24:
            n = s.length(); out = list(s.b[s.p:s.p+n]); s.p += n
        elif t == 25 or t == 4 or t == 22: raise NotImplementedError(t)
        else: raise NotImplementedError('type %d' % t)
        attrs = dict(s.item()) if has_attr else {}
        return ('vec', t, out, attrs)

def _to_df(obj):
    _, t, cols, attrs = obj
    names = attrs['names'][2]
    data = {}
    for n, c in zip(names, cols):
        vals, a = c[2], c[3]
        if 'levels' in a:
            lv = a['levels'][2]; vals = [None if v is None else lv[v - 1] for v in vals]
        data[n] = vals
    return pd.DataFrame(data)

def read_rdata(path):
    raw = open(path, 'rb').read()
    for opener in (lzma.decompress, gzip.decompress, bz2.decompress, lambda x: x):
        try: raw = opener(raw); break
        except Exception: continue
    assert raw[:5] in (b'RDX2\n', b'RDX3\n'), raw[:8]
    ver = raw[:4]; r = _R(raw); r.p = 5
    assert raw[5:7] == b'X\n'; r.p = 7
    r.i32(); r.i32(); r.i32()               # format version, writer ver, min reader ver
    if ver == b'RDX3':
        n = r.i32(); r.p += n               # native encoding
    top = r.item()
    return {name: _to_df(o) for name, o in top if isinstance(o, tuple) and 'names' in o[3]}
