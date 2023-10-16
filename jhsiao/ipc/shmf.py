"""mmap wrappers with focus on IPC.

Generally, this is 1 process creates in write mode
and multiple others read from the mmap

Generally, mmap should be created on a ramdisk to be used as shared
memory, but it will still work on a normal disk (though it may cause
wear on the disks... I assume that the testing I did on mmap and disk
files is what caused it to fail so quickly within a year of purchase...)

shmf uses non-file mappings.  On windows, this means anonymous mmaps
using tagnames to specify/share them.  On linux, it means using posix
shared memory (Although this does create a file, but in a tmpfs...).

Here, creating a mapping indicates mapping the space.  Opening a mapping
refers to opening the space for usage.  Users should indicate whether
the mapping should be created or whether they want to use an existing
mapping.  Mappings are treated as fixed-size.  If more space is
required, then close the current mapping and open a new one.

goals:
    Familiarize with mmapping as IPC.
    More efficient 1 to many IPC. (Write once and readers read
    concurrently.)
    file locking mechanism?

NOTE: resize FAILS on windows, implement without any resizing: create a new mapping
    if need larger map.

Windows:
    anonymous map... in memory only? (fd = -1) + tagname
    NOTE: size of 0 does not work in python with these tagged
    anonymous mappings.  The size must be queried, but the size
    is not exact (rounded up to pagesize it seems).  As a result,
    subsequent Shmfs may have larger size() than the original.
Linux:
    posix shared memory.  If fail, create a file in SHMFDIR env var
    or /dev/shm or /tmp.  (Can make a tmpfs and set SHMFDIR to use that)
    systemV: unimplemented for now
"""
from __future__ import print_function

import ctypes
import mmap
import platform
import os
import stat
import uuid

def setattrs(func, **kwargs):
    """Set attrs of func and return it.

    Useful for setting values for ctypes functions.
    """
    for k, v in kwargs.items():
        setattr(func, k, v)
    return func

class Utils(object):
    def get_mmap(self, identifier, mode, size, create):
        """Get an mmap.

        identifier: str
            the identifier of the mmap.
        mode: str
            The mode string. w, w+, r, r+
        size: int
            The size of the mmap.  Use 0 to indicate to the full size
            of the existing mmap.  0 requires that the mmap already
            exists.
        create: bool
            Create the mmap.
        """
        raise NotImplementedError

    def close_shmf(self, shmf):
        """Close the mmap and delete it if delete.

        mmp: mmap
            The mmap returned from `get_mmap`.
        delete: bool
            Same value as `create` in `get_mmap`
        """
        raise NotImplementedError

class _WindowsUtils(Utils):
    """Windows utilities.

    Python mmap is bugged where using size=0 with anonymous tagged mmap
    does not use the full mmap size but raise an exception instead.
    """
    FILE_MAP_READ = 0x0004
    try:
        # typedef struct _MEMORY_BASIC_INFORMATION {
        #  PVOID  BaseAddress;
        #  PVOID  AllocationBase;
        #  DWORD  AllocationProtect;
        #  WORD   PartitionId;
        #  SIZE_T RegionSize;
        #  DWORD  State;
        #  DWORD  Protect;
        #  DWORD  Type;
        # } MEMORY_BASIC_INFORMATION, *PMEMORY_BASIC_INFORMATION;
        class MEMORY_BASIC_INFORMATION(ctypes.Structure):
            _fields_ = (
                ('BaseAddress', ctypes.wintypes.LPVOID),
                ('AllocationBase', ctypes.wintypes.LPVOID),
                ('AllocationProtect', ctypes.wintypes.DWORD),
                ('PartitionId', ctypes.wintypes.WORD),
                ('RegionSize', ctypes.c_size_t),
                ('State', ctypes.wintypes.DWORD),
                ('Protect', ctypes.wintypes.DWORD),
                ('Type', ctypes.wintypes.DWORD))
        PMEMORY_BASIC_INFORMATION = ctypes.POINTER(MEMORY_BASIC_INFORMATION)
    except AttributeError:
        pass

    @staticmethod
    def errcheck_bool(result, func, args):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return args

    def __init__(self):
        wtypes = ctypes.wintypes
        self.k32 = ctypes.WinDLL('kernel32', use_last_error=True)

        # SIZE_T VirtualQuery(
        #   [in, optional] LPCVOID                   lpAddress,
        #   [out]          PMEMORY_BASIC_INFORMATION lpBuffer,
        #   [in]           SIZE_T                    dwLength
        # );
        self.VirtualQuery = setattrs(
            self.k32.VirtualQuery,
            errcheck=self.errcheck_bool,
            restype=ctypes.c_size_t,
            argtypes=(wtypes.LPCVOID, self.PMEMORY_BASIC_INFORMATION, ctypes.c_size_t))

        # HANDLE OpenFileMappingW(
        #   [in] DWORD   dwDesiredAccess,
        #   [in] BOOL    bInheritHandle,
        #   [in] LPCWSTR lpName
        # );
        self.OpenFileMappingW = setattrs(
            self.k32.OpenFileMappingW,
            errcheck=self.errcheck_bool,
            restype=wtypes.HANDLE,
            argtypes=(wtypes.DWORD, wtypes.BOOL, wtypes.LPCWSTR))

        # LPVOID MapViewOfFile(
        #   [in] HANDLE hFileMappingObject,
        #   [in] DWORD  dwDesiredAccess,
        #   [in] DWORD  dwFileOffsetHigh,
        #   [in] DWORD  dwFileOffsetLow,
        #   [in] SIZE_T dwNumberOfBytesToMap
        # );
        self.MapViewOfFile = setattrs(
            self.k32.MapViewOfFile,
            errcheck=self.errcheck_bool,
            restype=wtypes.LPVOID,
            argtypes=(wtypes.HANDLE, wtypes.DWORD, wtypes.DWORD, wtypes.DWORD, ctypes.c_size_t))

        # BOOL UnmapViewOfFile(
        #   [in] LPCVOID lpBaseAddress
        # );
        self.UnmapViewOfFile = setattrs(
            self.k32.UnmapViewOfFile,
            errcheck=self.errcheck_bool,
            restype=wtypes.BOOL,
            argtypes=(wtypes,LPCVOID,))

        # BOOL CloseHandle(
        #   [in] HANDLE hObject
        # );
        self.CloseHandle = setattrs(
            self.k32.CloseHandle,
            errcheck=self.errcheck_bool,
            restype=self.wtypes.BOOL,
            argtypes=(wtypes.HANDLE,))

    def get_mmap_size(self, tagname):
        """Get the actual mmap size.

        tagname: str
            The tag name of the mmap.
        """
        handle = self.OpenFileMappingW(self.FILE_MAP_READ, 0, tagname)
        try:
            p = self.MapViewOfFile(handle, self.FILE_MAP_READ, 0, 0, 0)
            try:
                mbi = MEMORY_BASIC_INFORMATION()
                self.VirtualQuery(
                    p, ctypes.byref(mbi),
                    ctypes.sizeof(MEMORY_BASIC_INFORMATION))
                return mbi.RegionSize
            finally:
                self.UnmapViewOfFile(p)
        finally:
            self.CloseHandle(handle)
        return 0

    def get_mmap(self, identifier, mode, size, create):
        if 'w' in mode or '+' in mode:
            access = mmap.ACCESS_WRITE
        else:
            access = mmap.ACCESS_READ
        if size == 0:
            size = self.get_mmap_size(identifier)
        return mmap.mmap(-1, size, tagname=identifier, access=access)

    @staticmethod
    def close_shmf(shmf):
        """Windows shmf mmaps does not require deleting anything."""
        shmf.mmap.close()

class _PosixUtils(object):
    def __init__(self):
        self.librt = ctypes.cdll.LoadLibrary('librt.so')
        self.shm_open = setattrs(
            self.librt.shm_open,
            argtypes=(ctypes.c_char_p, ctypes.c_int, ctypes.c_short),
            restype=ctypes.c_int)
        self.shm_unlink = setattrs(
            self.librt.shm_unlink,
            argtypes=(ctypes.c_char_p,),
            restype=ctypes.c_int)
        # for now, just user only
        self.permissions = (
            stat.S_IRUSR | stat.S_IWUSR
            # | stat.S_IRGRP | stat.S_IWGRP
            # | stat.S_IROTH | stat.S_IWOTH
        )

    @staticmethod
    def _throw():
        eno = ctypes.get_errno()
        if eno:
            raise OSError(eno, os.strerror(eno))
        else:
            raise OSError(eno, 'Unknown')

    def get_mmap(self, identifier, mode, size, create):
        flags = 0
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        if '+' in mode or 'w' in mode:
            # shm_open docs do not list os.O_WRONLY as a valid flag.
            # so only RDWR
            access = mmap.ACCESS_WRITE
            flags |= os.O_RDWR
        else:
            access = mmap.ACCESS_READ
            if create:
                # Creating initial size requires write permissions.
                flags |= os.O_RDWR
            else:
                flags |= os.O_RDONLY
        try:
            identifier = identifier.encode()
        except AttributeError:
            pass
        if not identifier.startswith(b'/'):
            identifier = b'/' + identifier
        fd = self.shm_open(identifier, flags, self.permissions)
        if fd == -1:
            self._throw()
        try:
            if create:
                os.ftruncate(fd, size)
            return mmap.mmap(fd, size, access=access)
        except Exception:
            if create:
                self.shm_unlink(identifier)
            raise
        finally:
            os.close(fd)

    def close_shmf(self, shmf):
        shmf.mmap.close()
        if shmf.created:
            try:
                n = shmf.name.encode()
            except AttributeError:
                n = shmf.name
            if not n.startswith(b'/'):
                n = b'/' + n
            if self.shm_unlink(n) == -1:
                self._throw()

# Abandoned research into using sysv shared memory
#    def trysysv():
#        """return classes for creating a shared buffer/file-like object
#
#        though may be more trouble than it's worth...
#        """
#        raise NotImplementedError
#        import ctypes
#        import subprocess
#        import re
#        libcname = re.search(
#            br'libc\.so\.[0-9]*',
#            subprocess.check_output(['ldd', sys.executable])).group()
#        libc = ctypes.cdll.LoadLibrary(libcname)
#        shmget = libc.shmget
#        shmat = libc.shmat
#        shmdt = libc.shmdt
#        shmctl = libc.shmctl
#        ftok = libc.ftok
#        # key_t ftok(const char *pathname, int proj_id);
#        # set types
#        # int shmget(key, size, shmflag)
#        shmget.argtypes = [ctypes.int, ctypes.c_size_t, ctypes.int]
#        shmget.restype = ctypes.int
#
#        # constants need to be hardcoded? or parsed from header...
#        # create file-like wrapper over buffer
#        def getmmap(size, mode, identifier=None):
#            pass
#        def closemmap(identifier, mm):
#            pass



# mmap.mmap is screwy as a class, so do not inherit from it.
# It has a __new__ that enforces creation signature so you cannot
# add arguments via __init__.  Furthermore, it disallows setting any
# attributes so you cannot add any attributes if you inherit from it.
class Shmf(object):
    if platform.system() == 'Windows':
        _utils = _WindowsUtils()
    else:
        _utils = _PosixUtils()

    def __init__(self, name=None, mode=None, size=0, create=None):
        """Initialize Shmf

        name: str|None
            The name of mmap to open.  If None, this indicates that a
            new mapping with a randomly generated name should be
            created.  In this case, size must be > 0.
        size: int>=0
            Size of mmap.  If 0, then the mmap MUST exist already (so
            name must not be None) and the full size of the existing
            mmap will be used.
        mode: str|None
            w, w+, r, or r+.  Unlike normal file modes, a and b are
            ignored because shmfs are always binary and do not get
            resized.  The default mode depends on name.  If None,
            it will be w+.  Otherwise, it will be r
        create: bool|None
            Indicate whether the mapping should be created.  If None,
            then default to True if w in mode, else False.
        """
        if name is None:
            if mode is None:
                mode = 'w+'
            if create is not None and not create:
                raise Exception('Name=None requires creation.')
            create = True
            if size == 0:
                raise ValueError('Name=None requires size > 0.')
            name = '/shmf' + uuid.uuid4().hex
        else:
            if mode is None:
                mode = 'r'
            if create is None:
                create = 'w' in mode
        self.created = create
        self.name = name
        try:
            self.mmap = self._utils.get_mmap(name, mode, size, create)
        except Exception:
            self.mmap = None
            raise

    def close(self):
        if self.mmap is not None:
            self._utils.close_shmf(self)
            self.created = False
            self.mmap = None

    def view(self):
        return memoryview(self.mmap)

    def __getattr__(self, name):
        """Act like a mmap."""
        ret = getattr(object.__getattribute__(self, 'mmap'), name)
        if callable(ret):
            setattr(self, name, ret)
        return ret

    def __buffer__(self, *args):
        return self.mmap.__buffer__(*args)
    def __release_buffer__(self, *args):
        return self.mmap.__release_buffer__(*args)

    def __getitem__(self, idx):
        return self.mmap[idx]
    def __setitem__(self, idx, val):
        self.mmap[idx] = val
    def __len__(self):
        return len(self.mmap)

    def __enter__(self):
        return self
    def __exit__(self, tp, exc, tb):
        self.close()
    def __del__(self):
        self.close()
