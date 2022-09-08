"""Simple Serialization for basic types

Note that type is not necessarily preserved.
eg. numpy.int32 -> FixedNum -> python int
types are tried raw, and then by isinstance.

preimplemented:
    ints
    floats
    str (utf-8)
    binary string (bytes, bytearray, memoryview, buffer (python2))

side notes:
    f.write(struct.pack(>BNX, idx, args))
    is slower than 2 f.writes regardless of the N value
    packinto is slow

    *args is slow if mixed with other args
    caching bytes and writing separately
    may be slower than a single pack together
"""
import struct
import sys
import pickle
import io
from itertools import chain
from functools import partial
from collections import deque
from numbers import Integral, Real

def bstructs(codes, pre='>', merge=True):
    """Return 2 lists of struct.Structs info.

    The first list has the appropriate struct.Struct and corresponding
    index into the second list for the same struct for loading.

    If merge is True, then the format will be prefixed with a single
    Byte as well indicating the index to use for unpacking.

    result = lst1[num.bit_length()][0].pack(num)
    lst2[lst1[num.bit_length()][1]].unpack(result)[0] == num
    If pre is blank, then struct will use "native" format
    (padding will be added for alignment)
    """
    base = [struct.Struct(pre+code) for code in codes]
    base.sort(key=(lambda x: x.size), reverse=True)
    # 1 item per possible bitlength, 8bits per byte
    if merge:
        structs = [(
            struct.Struct(pre + 'B' + base[0].format[len(pre):]), 0)]
    else:
        structs = [(base[0], 0)]
    structs *= base[0].size*8 + 1
    for lidx, s in enumerate(base[1:]):
        if merge:
            tup = (struct.Struct(pre + 'B' + s.format[len(pre):]), lidx+1)
        else:
            tup = (s, lidx+1)
        for i in range(s.size*8 + 1):
            structs[i] = tup
    return tuple(structs), tuple(base)

class BaseSerializer(object):
    """Base class for serializing a single type."""
    TYPES=()
    def __init__(self, top):
        """Initialize a type serializer.

        top: should be a general-item serializer.
            It will be used if the current type can
            possible contain a generic item.
        """
        pass

    # dump/load interface
    def dump(self, item, f):
        """Dump the item directly into the file-like object.

        May be replaced with a closure for performance so
        do not use the unbound versions.
        """
        raise NotImplementedError
    def load(self, f):
        """Load an item from file-like object.

        May be replaced with a closure for performance so
        do not use the unbound versions.
        """
        raise NotImplementedError

    # code-generation components
    def components(self, name):
        """Return a dict of values.

        name: the name of the variable to use in code.

        Considerations:
        1. data is split into fixed and variable portions.
            Fixed data can be packed in a single call for better efficiency
        2. some data should be retained as a sequence, others should be
            unpacked.  tuple-unpacking is faster than indexing.
            As a result, unpacked items should all be unpacked together.
            the ones that require maintaining the sequence should be
            separately unpacked since unpacking already returns a sequence.
            It is faster than a giant unpack and then a bunch of slicing.
        3. deserialization speed should probably be prioritized over
            serialization speed.  This way, a server would be better able to
            handle multiple clients.  If sending to multiple servers, you
            would just pack once anyways and send the same bytes.
        required info:
        1. sequence of fixed exprs for packing and corresponding struct
            format string.
        2. whether deserialized fixed portion should be unpacked or not.
        3. code to handle variable data
        4. a list of exprs for 
        The dict can contain:
            format: format-string in struct format.  (This should not
                contain any byte-order indicators since struct does not
                allow changing byte-order mid-format).
                If s = struct.Struct(format).size, then 
                len(s.unpack(bytearray(s.size))) should be the number of
                fixed-size values for serialization of this item.
            fixed: A list/tuple of expressions to be passed to
                struct.pack.  Alternatively, a string expression
                representing a sequence of items.  The number of items
                should correspond to format.
        optional keys:
            unpack: bool, True if the values should be unpacked

            prep: 
            data: This should be a sequence of bytes/binary
                expressions representing variable data, if any.
            local: This should be a dict of any required local variables.
        """
        # NOTES: did some profiling about unpacking/separating values.
        # 1. If unpacking to separate variables is required, then a
        #   single struct.unpack followed by tuple unpack is fastest
        #   even up to 2000 vars.
        # 2. If the chunk is needed as-is, then a separate unpack() call
        #   has the best performance
        # 3. even for single value, unpacking is faster than indexing
        #   (tested on python 3.9.1)
        raise NotImplementedError

class NONE(BaseSerializer):
    @staticmethod
    def dump(item, f):
        return
    @staticmethod
    def load(f):
        return None

class _FixedPrimitive(BaseSerializer):
    """Fixed size single primitive (ints, floats)."""
    @staticmethod
    def _make_closures(packer):
        pack = packer.pack
        unpack = packer.unpack
        size = packer.size

        @staticmethod
        def dump(item, f):
            f.write(pack(item))

        @staticmethod
        def load(f):
            return unpack(f.read(size))[0]

        @staticmethod
        def components(name):
            raise NotImplementedError

        return dump, load, components

class _FixedInt(_FixedPrimitive):
    TYPES = (int, Integral)

class Uint8(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>B'))
class Uint16(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>H'))
class Uint32(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>L'))
class Uint64(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>Q'))
class Int8(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>b'))
class Int16(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>h'))
class Int32(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>l'))
class Int64(_FixedInt):
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>q'))

class Float32(_FixedPrimitive):
    TYPES=(float, Real)
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>f'))
class Float64(_FixedPrimitive):
    TYPES=(float, Real)
    dump, load, components = _FixedPrimitive._make_closures(struct.Struct('>d'))

class PStruct(BaseSerializer):
    """Represents a sequence of data to be serialized via struct.Struct.

    Subclasses should have a class attribute FORMAT.
    """
    def __init__(self, top):
        self.TYPES = (type(self),)


class CompactNum(BaseSerializer):
    """1byte type + num, pick type based on size of number."""
    upstructs, ulstructs = bstructs('BHLQ', '>', False)
    ipstructs, ilstructs = bstructs('bhlq', '>', False)

class CompacterNum(CompactNum):
    """Tries to be smaller than CompactNum.

    Assumes small positive numbers are more common so 248-255 are
    reserved values indicating type. <248 means as-is
    """
    def __init__(self, top):
        upstructs = [(p.pack, idx) for p, idx in self.upstructs]
        bytepack = upstructs[0][0].pack
        byteunpack = upstructs[0][0].unpack
        loaders = [
            (p.unpack, p.size) for p in
            chain(self.ulstructs, self.ilstructs)]

        # total of 8 possible types
        # 248-255 are reserved to indicate more data
        # to be read, else use as is
        def dump(item, f):
            if item >= 0:
                if item < 248:
                    f.write(bytepack(item))
                    return
                else:
                    packer, idx = upstructs[item.bit_length()]
            else:

        if sys.version_info.major > 2:
            def load(f):
                v = f.read(1)[0]
                if v < 248:
                    return v
                v -= 248
                unpacks[v]
        else:
            def load(f):
                v = memoryview(f.read(1))[0]





class Any(BaseSerializer):
    """Any of the included types."""
    def __init__(self, types, top=None, size=None):
        super(Any, self).__init__(top)


class List(BaseSerializer):
    pass

class Tuple(BaseSerializer):
    pass




class Dict(BaseSerializer):
    def __init__(self, ):
        pass


def compile(thing):
    """Compile custom pack/unpack methods."""
    pass





# OLD IMPL

#  def NONE(top, dsize, lsize):
#      def dump(item, f):
#          pass
#      def load(f):
#          return None
#      return dump, load, (type(None),)
#  
#  def indep(ret, top, dsize, lsize):
#      """Serializers independent of top/dsize/lsize."""
#      return ret
#  
#  def Fixed(name, code, tp):
#      s = struct.Struct(code)
#      pack = s.pack
#      unpack = s.unpack
#      size = s.size
#  
#      def dump(item, f):
#          f.write(pack(item))
#  
#      def load(f):
#          return unpack(f.read(size))[0]
#      return dump, load, tp
#  Fixed = {
#      _[0]: partial(indep, Fixed(*_))
#      for _ in (
#          ('Int8', '>b', (int, Integral)),
#          ('Int16', '>h', (int, Integral)),
#          ('Int32', '>l', (int, Integral)),
#          ('Int64', '>q', (int, Integral)),
#          ('Uint8', '>B', (int, Integral)),
#          ('Uint16', '>H', (int, Integral)),
#          ('Uint32', '>L', (int, Integral)),
#          ('Uint64', '>Q', (int, Integral)),
#          ('Float32', '>f', (float, Real)),
#          ('Float64', '>d', (float, Real)))
#  }
#  
#  def CompactNum():
#      if 1:
#          UDUMP = []
#          IDUMP = []
#          LOAD = []
#          bytestruct = struct.Struct(b'>B')
#          for dumpers, codes in (
#                  (UDUMP, ('>B', '>H', '>L', '>Q')),
#                  (IDUMP, ('>b', '>h', '>l', '>q'))):
#              for i, code in enumerate(codes):
#                  if i:
#                      lo = hi
#                  else:
#                      lo = 0
#                  s = struct.Struct(code)
#                  hi = s.size*8 + 1
#                  idx = bytestruct.pack(len(LOAD))
#                  for _ in range(lo, hi):
#                      dumpers.append((idx, s.pack))
#                  LOAD.append((s.size, s.unpack))
#          DUMPS = (IDUMP, UDUMP)
#          def dump(item, f):
#              try:
#                  if item >= 0:
#                      idx, packer = UDUMP[item.bit_length()]
#                  else:
#                      idx, packer = IDUMP[(-1 - item).bit_length()+1]
#              except AttributeError:
#                  return dump(int(item), f)
#              except IndexError:
#                  f.write(bytestruct.pack(len(LOAD)))
#                  pickle.dump(item, f)
#              else:
#                  f.write(idx)
#                  f.write(packer(item))
#  
#          if sys.version_info.major > 2:
#              def load(f):
#                  try:
#                      size, unpacker = LOAD[f.read(1)[0]]
#                  except IndexError:
#                      return pickle.load(f)
#                  else:
#                      return unpacker(f.read(size))[0]
#          else:
#              def load(f):
#                  try:
#                      size, unpacker = LOAD[memoryview(f.read(1))[0]]
#                  except IndexError:
#                      return pickle.load(f)
#                  else:
#                      return unpacker(f.read(size))[0]
#  
#      else:
#          UINFO = (
#              (0xFF, b'>B'),
#              (0xFFFF, b'>H'),
#              (0xFFFFFFFF, b'>L'),
#              (0xFFFFFFFFFFFFFFFF, b'>Q'))
#          IINFO = (
#              (-1 - 0x7F, b'>b'),
#              (-1 - 0x7FFF, b'>h'),
#              (-1 - 0x7FFFFFFF, b'>l'),
#              (-1 - 0x7FFFFFFFFFFFFFFF, b'>q'))
#  
#          def dump(item, f):
#              if item >= 0:
#                  for thresh, code in UINFO:
#                      if item <= thresh:
#                          f.write(code)
#                          f.write(struct.pack(code, item))
#                          return
#                  f.write(b'<P')
#                  pickle.dump(item, f)
#              else:
#                  for thresh, code in IINFO:
#                      if item >= thresh:
#                          f.write(code)
#                          f.write(struct.pack(code, item))
#                          return
#                  f.write(b'<P')
#                  pickle.dump(item, f)
#  
#          def load(f):
#              code = f.read(2)
#              if code == b'<P':
#                  return pickle.load(f)
#              else:
#                  s = struct.Struct(code)
#                  return s.unpack(f.read(s.size))[0]
#      return dump, load, (int, Integral)
#  
#  CompactNum = partial(indep, CompactNum())
#  
#  def Binstr(top, dsize, lsize):
#      """A bytes."""
#      TYPES = (bytes, bytearray, memoryview)
#      if sys.version_info.major < 3:
#          TYPES += (buffer,)
#  
#      def dump(item, f):
#          dsize(len(item), f)
#          f.write(item)
#      def load(f):
#          return f.read(lsize(f))
#      return dump, load, TYPES
#  
#  def Str(top, dsize, lsize):
#      if sys.version_info.major > 2:
#          TYPES = (str,)
#      else:
#          TYPES = (unicode,)
#      def dump(item, f):
#          item = item.encode('utf-8')
#          dsize(len(item), f)
#          f.write(item)
#      def load(f):
#          return f.read(lsize(f)).decode('utf-8')
#      return dump, load, TYPES
#  
#  def SimpleList(top, dsize, lsize):
#      """Simple non-recursive list."""
#      tdump = top.dump
#      tload = top.load
#      def dump(item, f):
#          dsize(len(item), f)
#          for thing in item:
#              tdump(thing, f)
#      def load(f):
#          return [tload(f) for i in range(lsize(f))]
#      return dump, load, (list, tuple)
#  
#  def SimpleTuple(top, dsize, lsize):
#      """Simple non-recursive tuple."""
#      ldump, lload, _ = SimpleList(top, dsize, lsize)
#      def load(f):
#          return tuple(lload(f))
#      return ldump, load, (tuple,)
#  
#  def SimpleSet(top, dsize, lsize):
#      """Simple set."""
#      ldump, lload, _ = SimpleList(top, dsize, lsize)
#      def load(f):
#          return set(lload(f))
#      return ldump, load, (set,)
#  
#  def SimpleDict(top, dsize, lsize):
#      """Simple non-recursive dict."""
#      tdump = top.dump
#      tload = top.load
#      def dump(item, f):
#          dsize(len(item), f)
#          for k, v in item.items():
#              tdump(k, f)
#              tdump(v, f)
#      def load(f):
#          return {tload(f): tload(f) for i in range(lsize(f))}
#      return dump, load, (dict,)
#  
#  # TODO implement handling for recursive list/dict
#  
#  BASIC = (CompactNum, Binstr, Str, Fixed['Float64'],NONE)
#  
#  class Serializer(object):
#      """Serialize general items."""
#      class Pre(object):
#          def __init__(self, data):
#              self.data = data
#              def dump(f):
#                  f.write(data)
#              self.dump = dump
#          def dump(self, f):
#              f.write(self.data)
#  
#      def __init__(
#          self, serializers=BASIC+(SimpleTuple, SimpleSet, SimpleList, SimpleDict),
#          size=CompactNum):
#          """Initialize a Serializer.
#  
#          serializers: A sequence of functions with signature func(top, size)
#              which returns 3 items: dump, load, and tuple of types.
#              Order matters.
#          size: Same type as an item of serializers which is used for sizes.
#              Alternatively, an index into serializers to use.
#          dump/load methods are only applicable for Serializers with
#          matching arguments.
#  
#          size should be independent of the Serializer.
#          """
#          #closure is faster? testing
#          def dump(item, f, subclassok=True):
#              """Dump item to a file-like object."""
#              tp = type(item)
#              try:
#                  func, code = typemap[tp]
#              except KeyError:
#                  if subclassok:
#                      for otp in typemap:
#                          if issubclass(tp, otp):
#                              func, code = typemap[otp]
#                              break
#                      else:
#                          raise ValueError('Serialization of type {} is unknown'.format(tp))
#                      typemap[tp] = (func, code)
#                  else:
#                      raise ValueError('Serialization of type {} is unknown'.format(tp))
#              f.write(code)
#              func(item, f)
#          def load(f):
#              """Load from a file-like object."""
#              return codemap[f.read(codesize)](f)
#          self.dump = dump
#          self.load = load
#  
#          if isinstance(size, int):
#              size = serialiers[size]
#          typemap = self.typemap = {}
#          codemap = self.codemap = {}
#          dsize, lsize, _ = size(None, None, None)
#          coder = ustructs[len(serializers).bit_length()]
#          codesize = self.codesize = coder.size
#          for i, ser  in enumerate(serializers):
#              dump, load, types = ser(self, dsize, lsize)
#              code = coder.pack(i)
#              dumper = dump, code
#              for tp in types:
#                  typemap.setdefault(tp, dumper)
#              codemap[code] = load
#          typemap.setdefault(self.Pre, (self.Pre.dump, b''))
#  
#      def dump(self, item, f, subclassok=True):
#          """Dump item to a file-like object."""
#          tp = type(item)
#          try:
#              func, code = self.typemap[tp]
#          except KeyError:
#              if subclassok:
#                  for otp in self.typemap:
#                      if issubclass(tp, otp):
#                          func, code = self.typemap[otp]
#                          break
#                  else:
#                      raise ValueError('Serialization of type {} is unknown'.format(tp))
#                  # threadunsafe but can never use outdated value
#                  # so maybe okay?
#                  self.typemap[tp] = (func, code)
#              else:
#                  raise ValueError('Serialization of type {} is unknown'.format(tp))
#          f.write(code)
#          func(item, f)
#  
#      def load(self, f):
#          """Load from a file-like object."""
#          return self.codemap[f.read(self.codesize)](f)
#  
#  
#      def dumps(self, item, subclassok=True):
#          """Dump item to bytes."""
#          # or maybe even SeqWriter?
#          # followed by b''.join()
#          # would need profiling
#          with io.BytesIO() as f:
#              self.dump(item, f, subclassok)
#              return f.getvalue()
#  
#      def loads(self, data):
#          """Load item from bytes."""
#          # but this copies data?
#          # maybe try profiling with jhsiao.utils.fio.BytesReader?
#          # implemented in python but no copy
#          with io.BytesIO(data) as f:
#              return self.load(f)
#  
#      def __call__(self, tp, subclassokay=True):
#          """Return the appropriate dump/load method pair if any."""
#          try:
#              return self.typemap[tp]
#          except KeyError:
#              if subclassokay:
#                  for ser in self.serializers:
#                      tps = ser.TYPES
#                      if issubclass(tp, tps):
#                          ret = self.typemap[tp] = self.typemap[tps[0]]
#                          return ret
#              raise ValueError('Serialization of type {} is unknown'.format(tp))
#  
#      def __getitem__(self, code):
#          """Return appropriate load method from a code."""
#          return self.codemap[code]
#  
#  
#  def useq(item, q, idmap):
#      ids = [id(thing) for thing in item]
#      for p in zip(ids, item):
#          if p[0] not in idmap:
#              idmap[p[0]] = None
#              q.append(p)
#      return ids
#  def rtup(mapping, obj):
#      return tuple([mapping[i] for i in obj])
#  def rlist(mapping, obj):
#      return [mapping[i] for i in obj]
#  def rset(mapping, obj):
#      return set([mapping[i] for i in obj])
#  
#  def udict(item, q, idmap):
#      ids = []
#      for k, v in item.items():
#          kid = id(k)
#          vid = id(v)
#          ids.append(kid)
#          ids.append(vid)
#          if kid not in idmap:
#              idmap[kid] = None
#              q.append((kid, k))
#          if vid not in idmap:
#              idmap[vid] = None
#              q.append((vid, v))
#      return ids
#  
#  def rdict(item, mapping, obj):
#      objs = [mapping[i] for i in obj]
#      it = iter(objs)
#      item.update(zip(it, it))
#  
#  
#  class RSerializer(Serializer):
#      """Serialize recursive structures."""
#      def __init__(
#          self,
#          mutables=((useq, rlist, (list,)), (useq, rset, (set,))),
#          immutables=((useq, rtup, (tuple,)),),
#          serializers=BASIC,
#          size=CompactNum
#      ):
#          """Initialize Rserializer.
#  
#          mutables: a 3-tuple:
#              1. func(item, q, idmap):
#                  1. populate the q with new objects (not in idmap)
#                  2. return list of ids
#              2. func(mapping, obj):
#                  regenerate the object.
#                  mapping is {id: obj}
#              3. types
#          immutables: a 3-tuple:
#              1. func(item, q, idmap):
#                  1. populate the q with new objects (not in idmap)
#                  2. return list of ids
#              2. func(item, mapping, obj):
#                  update item from obj and mapping.
#              3. types
#          serializers:
#              Same as Serializer.  These should be non-recursible.
#              (Passing None as top should not error)
#          """
#          super(RSerializer, self).__init__(serializers)
#          superdump = self.dump
#          superload = self.load
#  
#          coder = struct.Struct(
#              mincode(len(mutables)+len(immutables)))
#          self.ufuncs = {}
#          self.rfuncs = {}
#          for cls in self.typemap:
#              self.ufuncs[cls] = None
#  
#          for i, (ufunc, rfunc, clss) in enumerate(mutables):
#              if set(clss).intersection(self.rollers):
#                  raise Exception('basic types and mutables overlap')
#              code = coder.pack(i)
#              r = code, ufunc
#              for tp in clss:
#                  self.rollers[tp] = code, ufunc
#              self.unrollers
#  
#  
#  
#  
#  # TODO
#  # generate a function to serialize a particular data structure
#  # argument = some object
#  # 1. find attributes and look for matches
#  # 2. generate code to serialize/deserialize that particular object
#  # 3. use this to serialize/deserialize that type (use the funcs
#  #   as part of a serializer?
#  #   things should be a type or None to indicate any
