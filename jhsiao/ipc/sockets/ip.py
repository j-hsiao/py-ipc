"""Getting ip addresses"""
__all__ = [
    'ipconfig',
    'ifconfig',
    'ipa',
    'default_ip',
    'get_ip',
]

import platform
import re
import socket
import subprocess
import sys

def _get_ip(cmd, header, search):
    """Return ips from header and search.

    Assume cmd output follows hanging indent conventions.
    cmd: commandline command to obtain ip info
    header: re.Pattern with 'device' group
    search: re.Pattern with 'ip' group
    """
    chunks = []
    data = subprocess.check_output(cmd).decode(sys.stdin.encoding)
    for line in data.splitlines():
        # ipconfig, ip, ifconfig all have
        # each section in similar format where 1st line is unindented
        # and following lines are
        if re.match(r'^\S', line):
            chunks.append([line])
        elif line.strip():
            chunks[-1].append(line)
    ret = {}
    for chunk in chunks:
        m = header.search(chunk[0])
        if m:
            name = m.group('device')
            ips = []
            for line in chunk[1:]:
                n = search.search(line)
                if n:
                    ips.append(n.group('ip'))
            if ips:
                ret[name] = ips
    return ret

def ipconfig(family='inet'):
    """Extract info from ipconfig."""
    winfam = {'inet': 'IPv4', 'inet6': 'IPv6'}[family]
    return _get_ip(
        ['ipconfig'],
        re.compile('adapter (?P<device>.*):'),
        re.compile('{} Address.*: (?P<ip>[a-fA-F0-9.:]+)'.format(winfam)))

def ifconfig(family='inet'):
    """Extract info from ifconfig."""
    return _get_ip(
        ['ifconfig'],
        re.compile('(?P<device>\\S+)'),
        re.compile('{} addr: ?(?P<ip>[a-fA-F0-9.:]+)'.format(family)))

def ipa(family='inet'):
    """Extract info from ip a."""
    return _get_ip(
        ['ip', 'a'],
        re.compile('\\d+: (?P<device>\\S+):'),
        re.compile('{} (?P<ip>[a-fA-F0-9.:]+)'.format(family)))

def default_ip(family='inet'):
    """Get ip info via udp broadcast."""
    if family == 'inet':
        fam, addr = socket.AF_INET, ('<broadcast>', 0)
    else:
        fam, addr = socket.AF_INET6, ('ffff::1', 80, 0, 0)
    try:
        s = socket.socket(fam, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.connect(addr)
        ret = s.getsockname()
        s.close()
        return ret[0]
    except Exception:
        return None

# NOTE: on windows, it seems like
# socket.getaddrinfo(socket.gethostname(), 0, socket.AF_INET) can return
# the ipv4 address and
# socket.getaddrinfo(socket.gethostname(), 0, socket.AF_INET6) can
# return the ipv6 addresses, but these fail on ubuntu where it just
# returns the values in /etc/hosts even if ip a and ifconfig show other
# addresses as well, and the values in /etc/hosts are incorrect.
def get_ip(family='inet'):
    """Return a dict of interface and ip for address family.


    family: str: 'inet' | 'inet6'
        The name of the address family to use.

    Output:
        {interfacename: [ip1, ip2, ip3,...],...}

    Information is gathered via subprocess by parsing output from:
        platform    commands
        Linux:      ip, ifconfig
        Windows:    ipconfig

    A udp broadcast socket will also be bound and the corresponding
    ip given under interface name "" (empty).

    The dict may be empty if no ips were found.
    """
    ret = {}
    try:
        bak = default_ip(family)
        if bak:
            ret[''] = [bak]
        if platform.system() == 'Windows':
            ret.update(ipconfig(family))
        else:
            try:
                ret.update(ipa(family))
            except Exception:
                ret.update(ifconfig(family))
    except Exception:
        pass
    return ret
