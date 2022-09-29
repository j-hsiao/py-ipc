"""Simple Serialization for basic types

Note that type is not necessarily preserved.
eg. numpy.int32 -> FixedNum -> python int
types are tried raw, and then by isinstance.

preimplemented:
    ints
    floats
    str (utf-8)
    binary string (bytes, bytearray, memoryview, buffer (python2))
"""
import struct
import sys
import pickle
import io
from functools import partial
from collections import deque
from numbers import Integral, Real

def NONE(top, dsize, lsize):
    def dump(item, f):
        pass
    def load(f):
        return None
    return dump, load, (type(None),)

def indep(ret, top, dsize, lsize):
    """Serializers independent of top/dsize/lsize."""
    return ret

def Fixed(name, code, tp):
    s = struct.Struct(code)
    pack = s.pack
    unpack = s.unpack
    size = s.size

    def dump(item, f):
        f.write(pack(item))

    def load(f):
        return unpack(f.read(size))[0]
    return dump, load, tp
Fixed = {
    _[0]: partial(indep, Fixed(*_))
    for _ in (
        ('Int8', '>b', (int, Integral)),
        ('Int16', '>h', (int, Integral)),
        ('Int32', '>l', (int, Integral)),
        ('Int64', '>q', (int, Integral)),
        ('Uint8', '>B', (int, Integral)),
        ('Uint16', '>H', (int, Integral)),
        ('Uint32', '>L', (int, Integral)),
        ('Uint64', '>Q', (int, Integral)),
        ('Float32', '>f', (float, Real)),
        ('Float64', '>d', (float, Real)))
}
def bstructs(codes, pre='>'):
    """Return list of structs of min-size by index=bitlength.

    Codes should be in decreasing order of size.
    Not very efficient for simplicity, but generally this is called
    once and the result cached.
    """
    base = [struct.Struct(pre+code) for code in codes]
    base.sort(key=(lambda x: x.size), reverse=True)
    structs = [base[0]] * (base[0].size*8 + 1)
    for s in base[1:]:
        for i in range(s.size*8 + 1):
            structs[i] = s
    return tuple(structs)

def CompactNum():
    if 1:
        UDUMP = []
        IDUMP = []
        LOAD = []
        bytestruct = struct.Struct(b'>B')
        for dumpers, codes in (
                (UDUMP, ('>B', '>H', '>L', '>Q')),
                (IDUMP, ('>b', '>h', '>l', '>q'))):
            for i, code in enumerate(codes):
                if i:
                    lo = hi
                else:
                    lo = 0
                s = struct.Struct(code)
                hi = s.size*8 + 1
                idx = bytestruct.pack(len(LOAD))
                for _ in range(lo, hi):
                    dumpers.append((idx, s.pack))
                LOAD.append((s.size, s.unpack))
        DUMPS = (IDUMP, UDUMP)
        def dump(item, f):
            try:
                if item >= 0:
                    idx, packer = UDUMP[item.bit_length()]
                else:
                    idx, packer = IDUMP[(-1 - item).bit_length()+1]
            except AttributeError:
                return dump(int(item), f)
            except IndexError:
                f.write(bytestruct.pack(len(LOAD)))
                pickle.dump(item, f)
            else:
                f.write(idx)
                f.write(packer(item))

        if sys.version_info.major > 2:
            def load(f):
                try:
                    size, unpacker = LOAD[f.read(1)[0]]
                except IndexError:
                    return pickle.load(f)
                else:
                    return unpacker(f.read(size))[0]
        else:
            def load(f):
                try:
                    size, unpacker = LOAD[memoryview(f.read(1))[0]]
                except IndexError:
                    return pickle.load(f)
                else:
                    return unpacker(f.read(size))[0]

    else:
        UINFO = (
            (0xFF, b'>B'),
            (0xFFFF, b'>H'),
            (0xFFFFFFFF, b'>L'),
            (0xFFFFFFFFFFFFFFFF, b'>Q'))
        IINFO = (
            (-1 - 0x7F, b'>b'),
            (-1 - 0x7FFF, b'>h'),
            (-1 - 0x7FFFFFFF, b'>l'),
            (-1 - 0x7FFFFFFFFFFFFFFF, b'>q'))

        def dump(item, f):
            if item >= 0:
                for thresh, code in UINFO:
                    if item <= thresh:
                        f.write(code)
                        f.write(struct.pack(code, item))
                        return
                f.write(b'<P')
                pickle.dump(item, f)
            else:
                for thresh, code in IINFO:
                    if item >= thresh:
                        f.write(code)
                        f.write(struct.pack(code, item))
                        return
                f.write(b'<P')
                pickle.dump(item, f)

        def load(f):
            code = f.read(2)
            if code == b'<P':
                return pickle.load(f)
            else:
                s = struct.Struct(code)
                return s.unpack(f.read(s.size))[0]
    return dump, load, (int, Integral)

CompactNum = partial(indep, CompactNum())

def Binstr(top, dsize, lsize):
    """A bytes."""
    TYPES = (bytes, bytearray, memoryview)
    if sys.version_info.major < 3:
        TYPES += (buffer,)

    def dump(item, f):
        dsize(len(item), f)
        f.write(item)
    def load(f):
        return f.read(lsize(f))
    return dump, load, TYPES

def Str(top, dsize, lsize):
    if sys.version_info.major > 2:
        TYPES = (str,)
    else:
        TYPES = (unicode,)
    def dump(item, f):
        item = item.encode('utf-8')
        dsize(len(item), f)
        f.write(item)
    def load(f):
        return f.read(lsize(f)).decode('utf-8')
    return dump, load, TYPES

def SimpleList(top, dsize, lsize):
    """Simple non-recursive list."""
    tdump = top.dump
    tload = top.load
    def dump(item, f):
        dsize(len(item), f)
        for thing in item:
            tdump(thing, f)
    def load(f):
        return [tload(f) for i in range(lsize(f))]
    return dump, load, (list, tuple)

def SimpleTuple(top, dsize, lsize):
    """Simple non-recursive tuple."""
    ldump, lload, _ = SimpleList(top, dsize, lsize)
    def load(f):
        return tuple(lload(f))
    return ldump, load, (tuple,)

def SimpleSet(top, dsize, lsize):
    """Simple set."""
    ldump, lload, _ = SimpleList(top, dsize, lsize)
    def load(f):
        return set(lload(f))
    return ldump, load, (set,)

def SimpleDict(top, dsize, lsize):
    """Simple non-recursive dict."""
    tdump = top.dump
    tload = top.load
    def dump(item, f):
        dsize(len(item), f)
        for k, v in item.items():
            tdump(k, f)
            tdump(v, f)
    def load(f):
        return {tload(f): tload(f) for i in range(lsize(f))}
    return dump, load, (dict,)

# TODO implement handling for recursive list/dict

BASIC = (CompactNum, Binstr, Str, Fixed['Float64'],NONE)

class Serializer(object):
    """Serialize general items."""
    class Pre(object):
        def __init__(self, data):
            self.data = data
            def dump(f):
                f.write(data)
            self.dump = dump
        def dump(self, f):
            f.write(self.data)

    def __init__(
        self, serializers=BASIC+(SimpleTuple, SimpleSet, SimpleList, SimpleDict),
        size=CompactNum):
        """Initialize a Serializer.

        serializers: A sequence of functions with signature func(top, size)
            which returns 3 items: dump, load, and tuple of types.
            Order matters.
        size: Same type as an item of serializers which is used for sizes.
            Alternatively, an index into serializers to use.
        dump/load methods are only applicable for Serializers with
        matching arguments.

        size should be independent of the Serializer.
        """
        #closure is faster? testing
        def dump(item, f, subclassok=True):
            """Dump item to a file-like object."""
            tp = type(item)
            try:
                func, code = typemap[tp]
            except KeyError:
                if subclassok:
                    for otp in typemap:
                        if issubclass(tp, otp):
                            func, code = typemap[otp]
                            break
                    else:
                        raise ValueError('Serialization of type {} is unknown'.format(tp))
                    typemap[tp] = (func, code)
                else:
                    raise ValueError('Serialization of type {} is unknown'.format(tp))
            f.write(code)
            func(item, f)
        def load(f):
            """Load from a file-like object."""
            return codemap[f.read(codesize)](f)
        self.dump = dump
        self.load = load

        if isinstance(size, int):
            size = serialiers[size]
        typemap = self.typemap = {}
        codemap = self.codemap = {}
        dsize, lsize, _ = size(None, None, None)
        coder = ustructs[len(serializers).bit_length()]
        codesize = self.codesize = coder.size
        for i, ser  in enumerate(serializers):
            dump, load, types = ser(self, dsize, lsize)
            code = coder.pack(i)
            dumper = dump, code
            for tp in types:
                typemap.setdefault(tp, dumper)
            codemap[code] = load
        typemap.setdefault(self.Pre, (self.Pre.dump, b''))

    def dump(self, item, f, subclassok=True):
        """Dump item to a file-like object."""
        tp = type(item)
        try:
            func, code = self.typemap[tp]
        except KeyError:
            if subclassok:
                for otp in self.typemap:
                    if issubclass(tp, otp):
                        func, code = self.typemap[otp]
                        break
                else:
                    raise ValueError('Serialization of type {} is unknown'.format(tp))
                # threadunsafe but can never use outdated value
                # so maybe okay?
                self.typemap[tp] = (func, code)
            else:
                raise ValueError('Serialization of type {} is unknown'.format(tp))
        f.write(code)
        func(item, f)

    def load(self, f):
        """Load from a file-like object."""
        return self.codemap[f.read(self.codesize)](f)


    def dumps(self, item, subclassok=True):
        """Dump item to bytes."""
        # or maybe even SeqWriter?
        # followed by b''.join()
        # would need profiling
        with io.BytesIO() as f:
            self.dump(item, f, subclassok)
            return f.getvalue()

    def loads(self, data):
        """Load item from bytes."""
        # but this copies data?
        # maybe try profiling with jhsiao.utils.fio.BytesReader?
        # implemented in python but no copy
        with io.BytesIO(data) as f:
            return self.load(f)

    def __call__(self, tp, subclassokay=True):
        """Return the appropriate dump/load method pair if any."""
        try:
            return self.typemap[tp]
        except KeyError:
            if subclassokay:
                for ser in self.serializers:
                    tps = ser.TYPES
                    if issubclass(tp, tps):
                        ret = self.typemap[tp] = self.typemap[tps[0]]
                        return ret
            raise ValueError('Serialization of type {} is unknown'.format(tp))

    def __getitem__(self, code):
        """Return appropriate load method from a code."""
        return self.codemap[code]


def useq(item, q, idmap):
    ids = [id(thing) for thing in item]
    for p in zip(ids, item):
        if p[0] not in idmap:
            idmap[p[0]] = None
            q.append(p)
    return ids
def rtup(mapping, obj):
    return tuple([mapping[i] for i in obj])
def rlist(mapping, obj):
    return [mapping[i] for i in obj]
def rset(mapping, obj):
    return set([mapping[i] for i in obj])

def udict(item, q, idmap):
    ids = []
    for k, v in item.items():
        kid = id(k)
        vid = id(v)
        ids.append(kid)
        ids.append(vid)
        if kid not in idmap:
            idmap[kid] = None
            q.append((kid, k))
        if vid not in idmap:
            idmap[vid] = None
            q.append((vid, v))
    return ids

def rdict(item, mapping, obj):
    objs = [mapping[i] for i in obj]
    it = iter(objs)
    item.update(zip(it, it))


class RSerializer(Serializer):
    """Serialize recursive structures."""
    def __init__(
        self,
        mutables=((useq, rlist, (list,)), (useq, rset, (set,))),
        immutables=((useq, rtup, (tuple,)),),
        serializers=BASIC,
        size=CompactNum
    ):
        """Initialize Rserializer.

        mutables: a 3-tuple:
            1. func(item, q, idmap):
                1. populate the q with new objects (not in idmap)
                2. return list of ids
            2. func(mapping, obj):
                regenerate the object.
                mapping is {id: obj}
            3. types
        immutables: a 3-tuple:
            1. func(item, q, idmap):
                1. populate the q with new objects (not in idmap)
                2. return list of ids
            2. func(item, mapping, obj):
                update item from obj and mapping.
            3. types
        serializers:
            Same as Serializer.  These should be non-recursible.
            (Passing None as top should not error)
        """
        super(RSerializer, self).__init__(serializers)
        superdump = self.dump
        superload = self.load

        coder = struct.Struct(
            mincode(len(mutables)+len(immutables)))
        self.ufuncs = {}
        self.rfuncs = {}
        for cls in self.typemap:
            self.ufuncs[cls] = None

        for i, (ufunc, rfunc, clss) in enumerate(mutables):
            if set(clss).intersection(self.rollers):
                raise Exception('basic types and mutables overlap')
            code = coder.pack(i)
            r = code, ufunc
            for tp in clss:
                self.rollers[tp] = code, ufunc
            self.unrollers




# TODO
# generate a function to serialize a particular data structure
# argument = some object
# 1. find attributes and look for matches
# 2. generate code to serialize/deserialize that particular object
# 3. use this to serialize/deserialize that type (use the funcs
#   as part of a serializer?
#   things should be a type or None to indicate any
