"""mmap classes with focus on IPC.

Generally, this is 1 process creates in write mode
and multiple others read from the mmap

Generally, mmap should be created on a ramdisk to be used as shared
memory, but it will still work on a normal disk (though it may cause
wear on the disks... I assume that the testing I did on mmap and disk
files is what caused it to fail so quickly within a year of purchase...)

Mappings are created when using with w or a exactly once.  All other
mappings should use r or r+.  When the intitial mapping is closed, all
other mappings are considered invalid.  Continuing to use them is
undefined behavior.  Opening mappings without w or a before the
initial w/a opening is also undefined behavior.  Mappings are treated
as fixed-size.  Because mmap, a is treated same as w.
Mode should be str, bytes not handled.

If mode is None, then it will depend on size.
    size=0 -> mode='r'
    size>0 -> mode='w+'
size=0 implies use all of existing mmap.

That is to say:
    Open with:
        w / w+ / a / a+
    all subsequent mappings for the same identifier:
        r / r+
    any others are undefined
    b is ignored. (mmap always binary)

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
    fallback will try to use SHMFDIR env var if set.
    otherwise, look for /dev/shm or /tmp
   probably mount a tmpfs and use file
   OR posix shared memory?
   OR systemV shared memory (abandoned for now)
"""
from __future__ import print_function

import mmap
import platform


# internal interface:
# _getmmap(size, mode, identifier):
#   size: size of mmap to create
#   mode: mode to open in (write/read)
#   identifier: an identifier for the mmap.
#
#   If size, then create if non-existent
#       Identifier: tagged or anonymous mapping
#   Otherwise, open an existing mmap(0 is invalid mmap size)
#       (identifier must be given in this case)
#
# _closemmap(identifer, mm, rm):
#   identifier: identifier of mmap
#   mm: the mmap object
#   rm: remove the underlying file or not.
if platform.system() == 'Windows':
    def _get_mmap_size_maker():
        """Define mmap size retrieval functions."""
        import ctypes
        from ctypes import wintypes as wtypes
        # based on this: get mmap size because using 0 size does not work
        # https://stackoverflow.com/questions/31495461/mmap-cant-attach-to-existing-region-without-knowing-its-size-windows
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)

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
                ('BaseAddress', wtypes.LPVOID),
                ('AllocationBase', wtypes.LPVOID),
                ('AllocationProtect', wtypes.DWORD),
                ('PartitionId', wtypes.WORD),
                ('RegionSize', ctypes.c_size_t),
                ('State', wtypes.DWORD),
                ('Protect', wtypes.DWORD),
                ('Type', wtypes.DWORD))
        PMEMORY_BASIC_INFORMATION = ctypes.POINTER(MEMORY_BASIC_INFORMATION)

        def errcheck_bool(result, func, args):
            if not result:
                raise ctypes.WinError(ctypes.get_last_error())
            return args
        # SIZE_T VirtualQuery(
        #   [in, optional] LPCVOID                   lpAddress,
        #   [out]          PMEMORY_BASIC_INFORMATION lpBuffer,
        #   [in]           SIZE_T                    dwLength
        # );
        VirtualQuery = k32.VirtualQuery
        VirtualQuery.errcheck = errcheck_bool
        VirtualQuery.restype = ctypes.c_size_t
        VirtualQuery.argtypes = (
            wtypes.LPCVOID, PMEMORY_BASIC_INFORMATION, ctypes.c_size_t)

        # HANDLE OpenFileMappingW(
        #   [in] DWORD   dwDesiredAccess,
        #   [in] BOOL    bInheritHandle,
        #   [in] LPCWSTR lpName
        # );
        OpenFileMappingW = k32.OpenFileMappingW
        OpenFileMappingW.errcheck = errcheck_bool
        OpenFileMappingW.restype = wtypes.HANDLE
        OpenFileMappingW.argtypes = (wtypes.DWORD, wtypes.BOOL, wtypes.LPCWSTR)

        # LPVOID MapViewOfFile(
        #   [in] HANDLE hFileMappingObject,
        #   [in] DWORD  dwDesiredAccess,
        #   [in] DWORD  dwFileOffsetHigh,
        #   [in] DWORD  dwFileOffsetLow,
        #   [in] SIZE_T dwNumberOfBytesToMap
        # );
        MapViewOfFile = k32.MapViewOfFile
        MapViewOfFile.errcheck = errcheck_bool
        MapViewOfFile.restype = wtypes.LPVOID
        MapViewOfFile.argtypes = (
            wtypes.HANDLE, wtypes.DWORD, wtypes.DWORD, wtypes.DWORD, ctypes.c_size_t)

        # BOOL UnmapViewOfFile(
        #   [in] LPCVOID lpBaseAddress
        # );
        UnmapViewOfFile = k32.UnmapViewOfFile
        UnmapViewOfFile.errcheck = errcheck_bool
        UnmapViewOfFile.restype = wtypes.BOOL
        UnmapViewOfFile.argtypes = (wtypes.LPCVOID,)

        # BOOL CloseHandle(
        #   [in] HANDLE hObject
        # );
        CloseHandle = k32.CloseHandle
        CloseHandle.errcheck = errcheck_bool
        CloseHandle.restype = wtypes.BOOL
        CloseHandle.argtypes = (wtypes.HANDLE,)

        FILE_MAP_READ = 0x0004
        def _get_mmap_size(tagname):
            """Get existing mmap's size.

            Because python has a bug where 0 size with existing tagged
            anonymous mmap fails.  Must find the size.
            """
            if not isinstance(tagname, str):
                tagname = tagname.decode()
            handle = OpenFileMappingW(FILE_MAP_READ, 0, tagname)
            try:
                p = MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 0)
                try:
                    mbi = MEMORY_BASIC_INFORMATION()
                    VirtualQuery(
                        p, ctypes.byref(mbi),
                        ctypes.sizeof(MEMORY_BASIC_INFORMATION))
                    return mbi.RegionSize
                finally:
                    UnmapViewOfFile(p)
            finally:
                CloseHandle(handle)
            return 0
        return _get_mmap_size

    _get_mmap_size = _get_mmap_size_maker()

    def _getmmap(size, mode, identifier):
        """Return an mmap.

        size: the size to use when opening the mmap.
            The mmap must already exist if size is 0.
        mode: open mode (rwa+) mmaps are binary
            mmaps are always readable
        identifier: the identifier for the mmap.
        """
        if size == 0:
            size = _get_mmap_size(identifier)
        if set('wa+').intersection(mode):
            access = mmap.ACCESS_WRITE
        else:
            access = mmap.ACCESS_READ
        return identifier, mmap.mmap(-1, size, tagname=identifier, access=access)
    def _closemmap(identifier, mm, rm):
        """Windows handles removal automatically."""
        mm.close()
else:
    import sys
    import traceback

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
#
#        # constants need to be hardcoded? or parsed from header...
#        # create file-like wrapper over buffer
#        def getmmap(size, mode, identifier=None):
#            pass
#        def closemmap(identifier, mm):
#            pass

    def _get_funcs(open_fd, remove):
        """Define the get/close mmap functions."""
        import stat
        import os
        def _getmmap(size, mode, identifier):
            """get an mmap with file-like arguments.

            size: size of desired mmap
            mode: the open mode rwa+, mmaps are binary
            identifier: an identifier for the mmap.
            """
            flags = 0
            explicit_create = set('wa').intersection(mode)
            if explicit_create:
                if not size:
                    raise Exception('creating mmap with size 0 not allowed')
                flags |= os.O_CREAT | os.O_EXCL
            if set('wa+').intersection(mode):
                access = mmap.ACCESS_WRITE
                flags |= os.O_RDWRA
            else:
                access = mmap.ACCESS_READ
                flags |= os.O_RDONLY
            name, fd = open_fd(identifier, flags, stat.S_IRUSR|stat.S_IWUSR)
            try:
                if os.O_EXCL & flags:
                    os.ftruncate(fd, size)
                return name, mmap.mmap(fd, size, access=access)
            finally:
                os.close(fd)

        def _closemmap(identifier, mm, rm):
            """Close and maybe remove mmap."""
            mm.close()
            if rm:
                remove(identifier)
        return _getmmap, _closemmap

    def trypos():
        """Try posix shared memory (shm_open/shm_unlink)"""
        import ctypes
        import stat
        import os
        import io
        librt = ctypes.cdll.LoadLibrary('librt.so')
        # int shm_open(const char *name, int oflag, mode_t mode);
        _shm_open = librt.shm_open
        _shm_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_short]
        _shm_open.restype = ctypes.c_int
        # int shm_unlink(const char *name);
        _shm_unlink = librt.shm_unlink
        _shm_unlink.argtypes = [ctypes.c_char_p]
        _shm_unlink.restype = ctypes.c_int
        py3 = sys.version_info.major > 2

        # Note... for some reason ctypes.get_errno() always returns 0
        # even if fd was -1.

        # writing mmap requires read too
        def open_fd(name, flags, mode):
            """Wrap shm_open

            name: filename
            flags: file flags (O_CREAT, O_READONLY/O_RDWR, etc)
            mode: file permissions mode

            It seems like essentially shm_open just creates a file in
            /dev/shm but may be more portable?
            """
            if isinstance(name, str) and py3:
                name = name.encode('utf-8')
            fd = _shm_open(name, flags, mode)
            if fd == -1:
                eno = ctypes.get_errno()
                if eno:
                    raise OSError(eno, os.strerror(eno))
                else:
                    raise OSError(eno, 'unknown')
            return name, fd
        def unlink(name):
            """Remove an shm object."""
            if isinstance(name, str) and py3:
                name = name.encode('utf-8')
            if _shm_unlink(name) == -1:
                eno = ctypes.get_errno()
                if eno:
                    raise OSError(eno, os.strerror(eno))
                else:
                    raise OSError(eno, 'unknown')
        return _get_funcs(open_fd, unlink)

    def fallback():
        """Same as posix shared_memory except...

        Try to use /dev/shm, then fall back to /tmp if not found.
        """
        import os
        customdir = os.environ.get('SHMFDIR')
        if customdir:
            SHMDIR = os.path.abspath(customdir)
        elif os.path.isdir('/dev/shm'):
            SHMDIR = '/dev/shm'
        else:
            SHMDIR = '/tmp'
        print(
            'warning, using fallback shmf impl, try to make sure "',
            SHMDIR, '" is a ramdisk or something.',
            file=sys.stderr)
        def open_fd(name, flags, mode):
            fname = os.path.join(SHMDIR, name)
            return fname, os.open(fname, flags, mode)
        return _get_funcs(open_fd, os.remove)

    try:
        _getmmap, _closemmap = trypos()
    except Exception:
        _getmmap, _closemmap = fallback()


import uuid
# mmap.mmap is screwy as a class, so do not inherit from it.
# It has a __new__ that enforces creation signature so you cannot
# add arguments via __init__.  Furthermore, it disallows setting any
# attributes so you cannot add any attributes if you inherit from it.
class Shmf(object):
    # keep a reference to _closemmap
    _closemmap = staticmethod(_closemmap)
    def __init__(self, name=None, size=0, mode=None):
        """Initialize Shmf

        name: name of mmap to open.
        size: size of mm
        mode: str 'rwa+' (b is ignored, mmap always binary)

        If name is given or size is 0, then mode will
        default to 'r'.  Otherwise it defaults to 'w+'.
        name will default to a random string.
        """
        if mode is None:
            if name is not None or size == 0:
                mode = 'r'
            else:
                mode = 'w+'
        self._created = set('wa').intersection(mode)
        if self._created and not size:
            raise Exception('size cannot be 0 when creating an Shmf')
        if name is None:
            name = 'pyipc_shmf_'+uuid.uuid4().hex
        self.name, self.mmap = _getmmap(size, mode, name)

    def __getattr__(self, name):
        ret = getattr(self.mmap, name)
        if callable(ret):
            setattr(self, name, ret)
        return ret
    def __getitem__(self, idx):
        return self.mmap[idx]
    def __setitem__(self, idx, val):
        self.mmap[idx] = val
    def __enter__(self):
        return self
    def __exit__(self, tp, exc, tb):
        self.close()
    def close(self):
        self._closemmap(self.name, self.mmap, self._created)
        self._created = False
