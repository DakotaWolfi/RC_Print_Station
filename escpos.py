"""Byte-level helpers shared with the verified Epson receipt path."""


def feed_and_cut(mm):
    dots=round(mm*8)
    commands=[]
    while dots:
        step=min(240,dots)
        commands.append(b"\x1bJ"+bytes([step]))
        dots-=step
    return b"".join(commands)+b"\x1dV\x00"
