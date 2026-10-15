"""Static, non-executing pickle decoder for pandas/numpy wide tables.

The stream is walked opcode by opcode with ``pickletools.genops``. GLOBAL/STACK_GLOBAL only create symbolic
``Ref`` names; REDUCE/NEWOBJ/BUILD only create symbolic ``Node`` records. Nothing is imported, constructed,
called or executed. Afterwards a small interpreter recognises a closed allow-list of numpy/pandas reconstruction
patterns and rebuilds plain arrays from raw bytes. Any other global, opcode or shape is rejected (fail closed).
"""
import io
import os
import pickletools

import numpy as np


class UnsafePickle(ValueError):
    """The stream uses something outside the reviewed allow-list."""


class Ref:
    __slots__ = ("module", "name")

    def __init__(self, module, name):
        self.module, self.name = module, name

    @property
    def qual(self):
        return self.module + "." + self.name

    def __repr__(self):
        return "Ref(%s)" % self.qual


class Node:
    """A symbolic call/object: func(*args) or cls.__new__(*args), plus optional BUILD state."""
    __slots__ = ("kind", "func", "args", "kwargs", "state", "items", "setitems")

    def __init__(self, kind, func, args, kwargs=None):
        self.kind, self.func, self.args, self.kwargs = kind, func, args, kwargs
        self.state, self.items, self.setitems = None, [], []

    def __repr__(self):
        return "Node(%s %s)" % (self.kind, getattr(self.func, "qual", self.func))


class _Mark:
    pass


MARK = _Mark()

# Only references whose reconstruction the interpreter below understands are permitted. Names are matched exactly.
ALLOWED_GLOBALS = {
    "numpy.core.multiarray._reconstruct", "numpy._core.multiarray._reconstruct",
    "numpy.core.numeric._frombuffer", "numpy._core.numeric._frombuffer",
    "numpy.ndarray", "numpy.dtype",
    "numpy.core.multiarray.scalar", "numpy._core.multiarray.scalar",
    "pandas.core.frame.DataFrame", "pandas.core.series.Series",
    "pandas.core.internals.managers.BlockManager", "pandas.core.internals.managers.SingleBlockManager",
    "pandas._libs.internals._unpickle_block", "pandas.core.internals.blocks.new_block",
    "pandas._libs.internals.BlockPlacement",
    "pandas.core.indexes.base._new_Index", "pandas.core.indexes.base.Index",
    "pandas.core.indexes.range.RangeIndex", "pandas.core.indexes.numeric.Int64Index", "pandas.core.indexes.datetimes._new_DatetimeIndex",
    "pandas.core.indexes.datetimes.DatetimeIndex", "pandas.core.arrays.datetimes.DatetimeArray",
    "pandas._libs.arrays.__pyx_unpickle_NDArrayBacked",
    "pandas.core.arrays.string_.StringDtype", "pandas.core.arrays.string_.StringArray",
    "pandas.core.arrays.string_arrow.ArrowStringArray",
    "builtins.slice", "builtins.object", "copyreg._reconstructor", "_codecs.encode", "builtins.bytearray",
    "pandas._libs.tslibs.timestamps._unpickle_timestamp",
    # pandas 3 public re-exports and Arrow-backed string arrays (decoded from raw buffers only)
    "pandas.DataFrame", "pandas.Index", "pandas.DatetimeIndex", "pandas.StringDtype",
    "pandas.arrays.ArrowStringArray", "pandas.arrays.DatetimeArray", "pandas.arrays.StringArray",
    "pyarrow.lib._restore_array", "pyarrow.lib.type_for_alias", "pyarrow.lib.py_buffer", "pyarrow.lib.chunked_array",
}

ARROW_STRING_TYPES = {"string": np.dtype("<i4"), "utf8": np.dtype("<i4"), "large_string": np.dtype("<i8"),
                      "large_utf8": np.dtype("<i8")}

FORBIDDEN_OPS = {"INST", "OBJ", "EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID"}


BYTES_HEADER = {"BINBYTES8": 9, "BYTEARRAY8": 9, "BINBYTES": 5, "SHORT_BINBYTES": 2}


def _pread(fd, size, offset):
    """Positional read; Windows has no os.pread, so seek on the private descriptor instead."""
    if hasattr(os, "pread"):
        return os.pread(fd, size, offset)
    os.lseek(fd, offset, os.SEEK_SET)
    out = bytearray()
    while len(out) < size:
        block = os.read(fd, size - len(out))
        if not block:
            break
        out += block
    return bytes(out)


class Blob:
    """Skeleton-mode stand-in for a large byte payload: length, digest and file offset of the raw bytes."""
    __slots__ = ("size", "sha256", "offset")

    def __init__(self, raw, offset=None):
        import hashlib
        self.size, self.sha256, self.offset = len(raw), hashlib.sha256(raw).hexdigest(), offset

    def read(self, fd):
        """Re-read exactly these bytes from the same file (pread) and verify the digest."""
        import hashlib
        if self.offset is None:
            raise UnsafePickle("blob offset unknown")
        raw = _pread(fd, self.size, self.offset)
        if len(raw) != self.size or hashlib.sha256(raw).hexdigest() != self.sha256:
            raise UnsafePickle("blob changed on disk")
        return raw

    def __len__(self):
        return self.size

    def __repr__(self):
        return "Blob(%d)" % self.size


def symbolic_load(data, *, max_bytes=512 * 1024 ** 2, max_ops=20_000_000, allowed=ALLOWED_GLOBALS, skeleton_over=None):
    """Return the symbolic object tree of a pickle without executing it.

    ``data`` is bytes or a binary stream. With ``skeleton_over`` set, byte payloads larger than that many bytes
    are replaced by ``Blob`` (length + SHA-256) so multi-GB files can be described with bounded memory.
    """
    if isinstance(data, (bytes, bytearray)):
        if len(data) > max_bytes:
            raise UnsafePickle("pickle above byte budget")
        stream = io.BytesIO(data)
    else:
        stream = data
    stack, metastack, memo = [], [], {}
    ops = 0

    def pop_mark():
        nonlocal stack
        items = stack
        stack = metastack.pop()
        return items

    for opcode, arg, pos in pickletools.genops(stream):
        ops += 1
        if ops > max_ops:
            raise UnsafePickle("opcode budget exceeded")
        if pos is not None and pos > max_bytes:
            raise UnsafePickle("pickle above byte budget")
        if skeleton_over is not None and isinstance(arg, (bytes, bytearray)) and len(arg) > skeleton_over:
            arg = Blob(arg, pos + BYTES_HEADER[opcode.name] if opcode.name in BYTES_HEADER and pos is not None else None)
        name = opcode.name
        if name in FORBIDDEN_OPS:
            raise UnsafePickle("forbidden opcode " + name)
        if name in ("PROTO", "FRAME"):
            continue
        if name == "STOP":
            break
        if name == "MARK":
            metastack.append(stack)
            stack = []
        elif name in ("GLOBAL", "STACK_GLOBAL"):
            if name == "GLOBAL":
                module, qual = arg.split(" ", 1)
            else:
                qual = stack.pop()
                module = stack.pop()
            if not isinstance(module, str) or not isinstance(qual, str):
                raise UnsafePickle("malformed global")
            # allowed=None is audit mode: names are still only symbols, nothing is imported or called.
            if allowed is not None and module + "." + qual not in allowed:
                raise UnsafePickle("global not allowed: %s.%s" % (module, qual))
            stack.append(Ref(module, qual))
        elif name in ("NONE",):
            stack.append(None)
        elif name in ("NEWTRUE", "NEWFALSE"):
            stack.append(name == "NEWTRUE")
        elif name in ("INT", "BININT", "BININT1", "BININT2", "LONG", "LONG1", "LONG4"):
            stack.append(arg)
        elif name in ("FLOAT", "BINFLOAT"):
            stack.append(arg)
        elif name in ("STRING", "BINSTRING", "SHORT_BINSTRING", "UNICODE", "BINUNICODE", "SHORT_BINUNICODE",
                      "BINUNICODE8", "BINBYTES", "SHORT_BINBYTES", "BINBYTES8", "BYTEARRAY8"):
            stack.append(bytes(arg) if name == "BYTEARRAY8" and not isinstance(arg, Blob) else arg)
        elif name == "EMPTY_LIST":
            stack.append([])
        elif name == "EMPTY_DICT":
            stack.append({})
        elif name == "EMPTY_TUPLE":
            stack.append(())
        elif name == "EMPTY_SET":
            stack.append(set())
        elif name == "LIST":
            items = pop_mark()  # must run before `stack` is read: pop_mark rebinds it
            stack.append(list(items))
        elif name == "TUPLE":
            items = pop_mark()
            stack.append(tuple(items))
        elif name in ("TUPLE1", "TUPLE2", "TUPLE3"):
            n = int(name[-1])
            items = tuple(stack[-n:])
            del stack[-n:]
            stack.append(items)
        elif name == "DICT":
            items = pop_mark()
            stack.append(_pairs_to_dict(items))
        elif name == "APPEND":
            value = stack.pop()
            _append(stack[-1], [value])
        elif name == "APPENDS":
            items = pop_mark()
            _append(stack[-1], items)
        elif name == "SETITEM":
            value = stack.pop()
            key = stack.pop()
            _setitems(stack[-1], [key, value])
        elif name == "SETITEMS":
            items = pop_mark()
            _setitems(stack[-1], items)
        elif name == "ADDITEMS":
            items = pop_mark()
            target = stack[-1]
            if not isinstance(target, set):
                raise UnsafePickle("ADDITEMS on non-set")
            target.update(i for i in items if _hashable(i))
        elif name == "FROZENSET":
            items = pop_mark()
            stack.append(frozenset(i for i in items if _hashable(i)))
        elif name in ("PUT", "BINPUT", "LONG_BINPUT"):
            memo[arg] = stack[-1]
        elif name == "MEMOIZE":
            memo[len(memo)] = stack[-1]
        elif name in ("GET", "BINGET", "LONG_BINGET"):
            stack.append(memo[arg])
        elif name == "POP":
            stack.pop()
        elif name == "POP_MARK":
            pop_mark()
        elif name == "DUP":
            stack.append(stack[-1])
        elif name == "REDUCE":
            args = stack.pop()
            func = stack.pop()
            if not isinstance(func, Ref) or not isinstance(args, tuple):
                raise UnsafePickle("REDUCE on non-reference")
            stack.append(Node("call", func, args))
        elif name == "NEWOBJ":
            args = stack.pop()
            cls = stack.pop()
            if not isinstance(cls, Ref):
                raise UnsafePickle("NEWOBJ on non-reference")
            stack.append(Node("new", cls, args))
        elif name == "NEWOBJ_EX":
            kwargs = stack.pop()
            args = stack.pop()
            cls = stack.pop()
            if not isinstance(cls, Ref):
                raise UnsafePickle("NEWOBJ_EX on non-reference")
            stack.append(Node("new", cls, args, kwargs))
        elif name == "BUILD":
            state = stack.pop()
            target = stack[-1]
            if not isinstance(target, Node):
                raise UnsafePickle("BUILD on non-object")
            target.state = state
        elif name == "NEXT_BUFFER" or name == "READONLY_BUFFER":
            raise UnsafePickle("out-of-band buffers are not supported")
        else:
            raise UnsafePickle("unsupported opcode " + name)
    if len(stack) != 1:
        raise UnsafePickle("malformed stream")
    return stack[0]


def _hashable(value):
    try:
        hash(value)
        return True
    except TypeError:
        return False


def _pairs_to_dict(items):
    out = {}
    for k, v in zip(items[::2], items[1::2]):
        out[k if _hashable(k) else id(k)] = v
    return out


def _append(target, items):
    if isinstance(target, list):
        target.extend(items)
    elif isinstance(target, Node):
        target.items.extend(items)
    else:
        raise UnsafePickle("APPEND on unsupported target")


def _setitems(target, items):
    if isinstance(target, dict):
        target.update(_pairs_to_dict(items))
    elif isinstance(target, Node):
        target.setitems.extend(zip(items[::2], items[1::2]))
    else:
        raise UnsafePickle("SETITEM on unsupported target")


# ---------------------------------------------------------------- interpretation (allow-listed patterns only)

def _is(ref, *names):
    return isinstance(ref, Ref) and ref.name in names


def to_dtype(node):
    """numpy.dtype(<code>, False, True) with BUILD state (version, byteorder, ..., [metadata])."""
    if not (isinstance(node, Node) and _is(node.func, "dtype")):
        raise UnsafePickle("unexpected dtype encoding")
    code = node.args[0]
    if code in ("O4", "O8"):  # numpy pickles object dtype with the pointer size
        code = "O"
    if not isinstance(code, str) or code not in {"f8", "f4", "i8", "i4", "i2", "i1", "u8", "u4", "u1", "b1", "O", "M8", "m8", "U"}:
        if not (isinstance(code, str) and (code.startswith("U") or code.startswith("S"))):
            raise UnsafePickle("dtype not allowed: %r" % (code,))
    state = node.state or ()
    order = state[1] if len(state) > 1 and state[1] in ("<", ">", "|", "=") else "|"
    if code in ("M8", "m8"):
        unit = "ns"
        meta = state[8] if len(state) > 8 else None
        if isinstance(meta, dict):
            meta = next(iter(meta.values()), None)
        if isinstance(meta, tuple) and meta and isinstance(meta[0], (bytes, str)):
            unit = meta[0].decode() if isinstance(meta[0], bytes) else meta[0]
        return np.dtype("%s%s[%s]" % (order if order != "|" else "<", code, unit))
    if code.startswith("U") and len(code) > 1 or code.startswith("S"):
        return np.dtype((order if order in "<>" else "") + code)
    return np.dtype((order if order in "<>" else "") + code) if code not in ("O", "b1") else np.dtype(code)


def _payload(raw, fd):
    if isinstance(raw, Blob):
        if fd is None:
            raise UnsafePickle("payload skipped in skeleton mode")
        return raw.read(fd)
    return raw


def to_array(node, *, max_elements=200_000_000, fd=None):
    """Rebuild an ndarray from the _reconstruct+BUILD or _frombuffer pattern, from raw bytes only."""
    if not isinstance(node, Node):
        raise UnsafePickle("array expected")
    if node.kind == "call" and _is(node.func, "_reconstruct"):
        state = node.state
        if not (isinstance(state, tuple) and len(state) == 5):
            raise UnsafePickle("ndarray state malformed")
        _version, shape, dtype_node, fortran, raw = state
        raw = _payload(raw, fd)
        dtype = to_dtype(dtype_node)
        shape = tuple(int(x) for x in shape)
        n = int(np.prod(shape)) if shape else 1
        if n > max_elements:
            raise UnsafePickle("array above element budget")
        if dtype == np.dtype("O"):
            if not isinstance(raw, list) or len(raw) != n:
                raise UnsafePickle("object array payload malformed")
            values = np.empty(n, dtype=object)
            for i, v in enumerate(raw):
                values[i] = _plain(v)
            return values.reshape(shape, order="F" if fortran else "C")
        if not isinstance(raw, (bytes, bytearray)) or len(raw) != n * dtype.itemsize:
            raise UnsafePickle("numeric payload size mismatch")
        return np.frombuffer(raw, dtype=dtype).reshape(shape, order="F" if fortran else "C")
    if node.kind == "call" and _is(node.func, "_frombuffer"):
        buf, dtype_node, shape, order = node.args
        buf = _payload(buf, fd)
        dtype = to_dtype(dtype_node)
        shape = tuple(int(x) for x in shape)
        if not isinstance(buf, (bytes, bytearray)) or len(buf) != int(np.prod(shape)) * dtype.itemsize:
            raise UnsafePickle("buffer size mismatch")
        return np.frombuffer(buf, dtype=dtype).reshape(shape, order=order)
    raise UnsafePickle("unsupported array encoding: %r" % (node,))


def _plain(value):
    """Object-array members must be plain scalars (str/int/float/bool/None/bytes)."""
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, Node) and _is(value.func, "scalar"):
        dtype = to_dtype(value.args[0])
        raw = value.args[1]
        if isinstance(raw, (bytes, bytearray)) and len(raw) == dtype.itemsize:
            return np.frombuffer(raw, dtype=dtype)[0].item()
    raise UnsafePickle("object array member not plain: %r" % (value,))


def iter_nodes(obj, _seen=None):
    """Yield every Node reachable from obj (args, kwargs, state, items)."""
    seen = _seen if _seen is not None else set()
    todo = [obj]
    while todo:
        cur = todo.pop()
        if isinstance(cur, Node):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            yield cur
            todo.extend([cur.args, cur.kwargs, cur.state, cur.items, cur.setitems])
        elif isinstance(cur, (list, tuple, set, frozenset)):
            todo.extend(cur)
        elif isinstance(cur, dict):
            todo.extend(cur.keys())
            todo.extend(cur.values())


def _buffer(node):
    if node is None:
        return None
    if isinstance(node, Node) and _is(node.func, "py_buffer") and isinstance(node.args[0], (bytes, bytearray)):
        return bytes(node.args[0])
    raise UnsafePickle("arrow buffer encoding not recognised")


def arrow_strings(node, *, max_elements=50_000_000):
    """Decode pyarrow _restore_array((type_for_alias(t), length, null_count, offset, buffers, children, dict))."""
    if isinstance(node, Node) and _is(node.func, "chunked_array"):
        chunks = node.args[0]
        if not isinstance(chunks, list):
            raise UnsafePickle("chunked array malformed")
        parts = [arrow_strings(c, max_elements=max_elements) for c in chunks]
        return np.concatenate(parts) if parts else np.empty(0, dtype=object)
    if not (isinstance(node, Node) and _is(node.func, "_restore_array") and len(node.args) == 1):
        raise UnsafePickle("arrow array encoding not recognised")
    spec = node.args[0]
    if not (isinstance(spec, tuple) and len(spec) == 7):
        raise UnsafePickle("arrow array spec malformed")
    typ, length, null_count, offset, buffers, children, dictionary = spec
    if not (isinstance(typ, Node) and _is(typ.func, "type_for_alias") and typ.args[0] in ARROW_STRING_TYPES):
        raise UnsafePickle("only arrow string arrays are allowed")
    if children or dictionary is not None or not isinstance(buffers, list) or len(buffers) != 3:
        raise UnsafePickle("arrow string layout malformed")
    if not (isinstance(length, int) and 0 <= length <= max_elements and isinstance(offset, int) and offset >= 0):
        raise UnsafePickle("arrow length/offset invalid")
    validity, offsets_raw, data = (_buffer(b) for b in buffers)
    off_dtype = ARROW_STRING_TYPES[typ.args[0]]
    offsets = np.frombuffer(offsets_raw or b"", dtype=off_dtype)
    if len(offsets) < offset + length + 1:
        raise UnsafePickle("arrow offsets too short")
    offsets = offsets[offset:offset + length + 1].astype(np.int64)
    data = data or b""
    if (np.diff(offsets) < 0).any() or offsets[-1] > len(data) or offsets[0] < 0:
        raise UnsafePickle("arrow offsets inconsistent")
    valid = None
    if validity is not None:
        bits = np.unpackbits(np.frombuffer(validity, dtype=np.uint8), bitorder="little")
        if len(bits) < offset + length:
            raise UnsafePickle("arrow validity bitmap too short")
        valid = bits[offset:offset + length].astype(bool)
    out = np.empty(length, dtype=object)
    for i in range(length):
        out[i] = None if valid is not None and not valid[i] else data[offsets[i]:offsets[i + 1]].decode("utf-8")
    if null_count not in (-1, int(sum(v is None for v in out))):
        raise UnsafePickle("arrow null count mismatch")
    return out


def _index_values(node):
    """Decode a pandas Index: _new_Index(cls, {'data': ndarray|DatetimeArray|ArrowStringArray, 'name': ...})."""
    if isinstance(node, Node) and node.kind == "call" and _is(node.func, "_new_Index", "_new_DatetimeIndex"):
        cls, payload = node.args[0], node.args[1]
        if not isinstance(payload, dict) or "data" not in payload:
            raise UnsafePickle("index payload malformed")
        data = payload["data"]
        if isinstance(data, Node) and _is(data.func, "_reconstruct", "_frombuffer"):
            return to_array(data), payload.get("name"), cls.name
        if isinstance(data, Node) and _is(data.func, "ArrowStringArray") and isinstance(data.state, dict):
            return arrow_strings(data.state.get("_pa_array")), payload.get("name"), cls.name
        if isinstance(data, Node) and _is(data.func, "__pyx_unpickle_NDArrayBacked", "DatetimeArray", "_reconstructor"):
            for inner in iter_nodes(data):
                if _is(inner.func, "_reconstruct", "_frombuffer"):
                    return to_array(inner), payload.get("name"), cls.name
        raise UnsafePickle("index data encoding not recognised")
    raise UnsafePickle("index expected")


def decode_frame(data, **limits):
    """Decode a pickled pandas DataFrame into (index, columns, {dtype: 2-D values aligned to columns})."""
    return frame_from_node(symbolic_load(data, **limits))


def frame_from_node(root, fd=None):
    """Interpret one symbolic DataFrame node; Blob payloads are pread from fd when given."""
    if not (isinstance(root, Node) and _is(root.func, "_reconstructor", "DataFrame") or isinstance(root, Node) and root.kind == "new"):
        raise UnsafePickle("root is not a pandas object")
    state = root.state
    mgr = state.get("_mgr") if isinstance(state, dict) else None
    if mgr is None and isinstance(state, dict):
        mgr = next((v for v in state.values() if isinstance(v, Node) and _is(v.func, "BlockManager")), None)
    if not (isinstance(mgr, Node) and _is(mgr.func, "BlockManager")):
        raise UnsafePickle("BlockManager not found")
    mstate = mgr.state
    if mgr.kind == "call" and len(mgr.args) == 2 and mstate is None:
        # pandas >= 2: BlockManager(blocks, axes) with blocks = (_unpickle_block(values, placement, ndim), ...)
        blocks, axes = mgr.args
        blocks = [dict(values=b.args[0], mgr_locs=b.args[1]) if isinstance(b, Node) and _is(b.func, "_unpickle_block", "new_block")
                  else b for b in blocks]
    elif isinstance(mstate, tuple) and len(mstate) >= 4 and isinstance(mstate[3], dict) and (
            "axes" in mstate[3] or "0.14.1" in mstate[3]):
        # pandas 0.20-1.x: state (axes, values, items, {'0.14.1': {'axes': [...], 'blocks': [{'values', 'mgr_locs'}]}})
        extra = mstate[3].get("0.14.1", mstate[3])
        if not isinstance(extra, dict) or "axes" not in extra or "blocks" not in extra:
            raise UnsafePickle("legacy BlockManager state malformed")
        axes, blocks = extra["axes"], extra["blocks"]
    else:
        raise UnsafePickle("BlockManager state malformed")
    if not (isinstance(axes, list) and len(axes) == 2):
        raise UnsafePickle("DataFrame axes malformed")
    columns, col_name, _ = _index_values(axes[0])
    index, idx_name, idx_cls = _index_values(axes[1])
    out = {}
    for block in blocks:
        if not isinstance(block, dict):
            raise UnsafePickle("block encoding not recognised")
        values, locs = block["values"], block.get("mgr_locs")
        arr = to_array(values, fd=fd) if _is(getattr(values, "func", None), "_reconstruct", "_frombuffer") else None
        if arr is None:
            raise UnsafePickle("block values encoding not recognised")
        if arr.ndim != 2 or arr.shape[1] != len(index):
            raise UnsafePickle("block shape does not match index")
        positions = _placement(locs, arr.shape[0])
        out.setdefault(str(arr.dtype), []).append((positions, arr))
    return dict(index=index, index_name=idx_name, index_class=idx_cls, columns=columns, columns_name=col_name,
                blocks=out, root=root.func.qual)


def _placement(locs, n):
    if isinstance(locs, Node) and _is(locs.func, "slice"):
        start, stop, step = locs.args
        return np.arange(start or 0, stop, step or 1)
    if isinstance(locs, Node) and _is(locs.func, "_reconstruct", "_frombuffer"):
        return to_array(locs).astype(np.int64)
    if isinstance(locs, Node) and _is(locs.func, "BlockPlacement"):
        return _placement(locs.args[0], n)
    raise UnsafePickle("block placement not recognised")


def frame_matrix(decoded, dtype=None):
    """Assemble a dates x codes matrix (single-dtype frames only, the wide-table contract)."""
    if len(decoded["blocks"]) != 1:
        raise UnsafePickle("wide table must have exactly one dtype, found %s" % sorted(decoded["blocks"]))
    (kind, parts), = decoded["blocks"].items()
    ncols = len(decoded["columns"])
    matrix = np.empty((len(decoded["index"]), ncols), dtype=parts[0][1].dtype)
    filled = np.zeros(ncols, dtype=bool)
    for positions, arr in parts:
        if len(positions) != arr.shape[0] or filled[positions].any():
            raise UnsafePickle("overlapping or inconsistent block placement")
        matrix[:, positions] = arr.T
        filled[positions] = True
    if not filled.all():
        raise UnsafePickle("columns not covered by blocks")
    return matrix
