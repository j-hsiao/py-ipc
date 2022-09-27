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

class BaseSerializer(object):
    """Base interface for serializing some type.

    TYPES must be a tuple.
    """
    TYPES = ()
    def __init__(self, code):
        self.code = code

    @staticmethod
    def dump(item, f, top):
        """serialize item into f.

        top is the toplevel serializer.
        """
        raise NotImplementedError
    @staticmethod
    def load(f, top):
        """deserialize item from f.

        top is the toplevel serializer.
        """
        raise NotImplementedError

class _FixedNum(BaseSerializer):
    """Fixed width number.

    Subclass should add a class attribute s which is a struct.Struct.
    """
    @classmethod
    def dump(cls, item, f, top):
        f.write(cls.s.dump(item))

    @classmethod
    def load(cls, f, top):
        s = cls.s
        return s.load(f.read(s.size))[0]

Fixed = {
    name: type(name, (_FixedNum,), dict(s=struct.Struct(code)))
    for name, code in (
        ('Int8', '>b'),
        ('Int16', '>h'),
        ('Int32', '>l'),
        ('Int64', '>q'),
        ('Uint8', '>B'),
        ('Uint16', '>H'),
        ('Uint32', '>L'),
        ('Uint64', '>Q'),
        ('Float32', '>f'),
        ('Float64', '>d'))
}
class CompactNum(BaseSerializer):
    """Use as few bytes as possible to store number."""
    TYPES = (int,)
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

    @classmethod
    def dump(cls, item, f, top):
        if item >= 0:
            for thresh, code in cls.UINFO:
                if item <= thresh:
                    f.write(code[1:])
                    f.write(struct.pack(code, item))
                    return
            f.write(b'P')
            pickle.dump(item, f)
        else:
            for thresh, code in cls.IINFO:
                if item >= thresh:
                    f.write(code[1:])
                    f.write(struct.pack(code, item))
                    return
            f.write(b'P')
            pickle.dump(item, f)

    @staticmethod
    def load(f, top):
        code = f.read(1)
        if code == b'P':
            return pickle.load(f)
        else:
            s = struct.Struct(b'>'+code)
            return s.unpack(f.read(s.size))[0]


class Binstr(BaseSerializer):
    """Serialize a bytes."""
    TYPES = (bytes, bytearray, memoryview)
    if sys.version_info.major < 3:
        TYPES += (buffer,)

    @staticmethod
    def dump(item, f, top):
        CompactNum.dump(len(item), f, top)
        f.write(item)

    @staticmethod
    def load(f, top):
        length = CompactNum.load(f, top)
        return f.read(length)

class Str(BaseSerializer):
    if sys.version_info.major > 2:
        TYPES = (str,)
    else:
        TYPES = (unicode,)

    @staticmethod
    def dump(item, f, top):
        Binstr.dump(item.encode('utf-8'), f, top)

    @staticmethod
    def load(f, top):
        return Binstr.load(f, top).decode('utf-8')


class List(BaseSerializer):
    TYPES = (list, tuple)

    @staticmethod
    def dump(item, f, top):
        CompactNum.dump(len(item), f, top)
        for thing in item:
            top.dump(thing, f)

    @staticmethod
    def load(f, top):
        return [top.load(f) for i in range(CompactNum.load(f, top))]


class Dict(BaseSerializer):
    pass


class Serializer(object):
    """Serialize general items."""
    def __init__(self, serializers=(CompactNum, Str, Binstr, Fixed['Float64'], List, Dict)):
        """Initialize a Serializer.

        load/dump must occur with the same serializers in the same
        order.  Earlier serializers with matching TYPES will be used
        first.  For example, if distinguishing between bytearray and
        bytes is important, then you should implement a BaseSerializer
        for bytearrays and put it earlier in the list of serializers
        """
        for thresh, code in CompactNum.UINFO:
            if len(serializers) <= thresh:
                s = struct.Struct(code)
                break
        else:
            raise Exception('too many types for serialization')
        self.typemap = {}
        self.codemap = {}
        self.sers = []
        for i, ser in enumerate(serializers):
            code = s.pack(i)
            dumper = ser.dump, code
            for tp in ser.TYPES:
                self.typemap.setdefault(tp, dumper)
            self.codemap[code] = ser.load

    def dump(self, item, f):
        """Dump item to a file-like object."""
        func, code = self(type(item))
        f.write(code)
        func(item, f, self)

    def load(self, f):
        """Load from a file-like object."""
        return self.codemap[f.read(1)](f, self)

    def dumps(self, item):
        """Dump item to bytes."""
        # or maybe even SeqWriter?
        # followed by b''.join()
        # would need profiling
        with io.BytesIO() as f:
            self.dump(item, f)
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
