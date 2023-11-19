"""Stream formats using generators.

yield will return None if next(), or the value if .send() is used.
This allows pause/resume of code when yield is encountered.

Read generators should yield a buffer to read into.
.send() should be used to communicate the amount of bytes read.

Writers...
"""

class Reader(object):
    pass
