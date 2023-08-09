"""Utility functions."""
__all__ = [
    'set_cloexec',
    'SOCK_CLOEXEC'
]

import platform
import socket
import sys


#------------------------------
# cloexec close socket in child processes
# example: without, child would keep server bound
#          if parent crashes, cannot rebind
#------------------------------
def set_cloexec():
    """Return a set_cloexec(sock, close) func."""
    if sys.version_info >= (3,4):
        def set_cloexec(sock, cloexec):
            """Set inheritability."""
            if sock.get_inheritable() != cloexec:
                sock.set_inheritable(cloexec)
    else:
        try:
            if platform.system() == 'Windows':
                from ctypes import windll, wintypes
                SetHandleInformation = windll.kernel32.SetHandleInformation
                SetHandleInformation.argtypes = [
                    wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
                SetHandleInformation.restype = wintypes.BOOL
                # from https://msdn.microsoft.com/en-us/library/windows/desktop/ms724935(v=vs.85).aspx
                HANDLE_FLAG_INHERIT = 1
                def set_cloexec(sock, cloexec):
                    """Set cloexec value for the socket."""
                    SetHandleInformation(
                        sock.fileno(), HANDLE_FLAG_INHERIT, 1-int(cloexec))
            else:
                import fcntl
                def set_cloexec(sock, cloexec):
                    """Set cloexec value for the socket."""
                    fd = sock.fileno()
                    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
                    if cloexec:
                        flags |= fcntl.FD_CLOEXEC
                    else:
                        flags &= ~fcntl.FD_CLOEXEC
                    fcntl.fcntl(fd, fcntl.F_SETFD, flags)
        except:
            warned = []
            def set_cloexec(sock, cloexec):
                if not warned:
                    warned.append(0)
                    print(
                        ('WARNING: set_cloexec could not be defined'
                        ' and cloexec will not be set'),
                        file = sys.stderr)
    return set_cloexec
set_cloexec = set_cloexec()
SOCK_CLOEXEC = getattr(socket, 'SOCK_CLOEXEC', 0)
# If socket has SOCK_CLOEXEC, then socket.socket() always returns
# non-inheritable socket so adding SOCK_CLOEXEC doesn't change anything
# right? If it's not defined, then the returned socket might be
# inheritable, but it's not defined anyways which means it wouldn't
# affect socket.socket() anyways, not sure.
