#! python2.7
# -*- coding: utf-8 -*-


# This script implements our old methods for merging an MD380 firmware
# image with its patches.  It is presently being rewritten to require
# fewer explicit addresses, so that we can target our patches to more
# than one version of the MD380 firmware.

from __future__ import print_function

import sys


class Symbols(object):
    addresses = {}
    names = {}

    def __init__(self, filename):
        print("Loading symbols from %s" % filename)
        fsyms = open(filename)
        for l in fsyms:
            try:
                r = l.strip().split('\t')
                if len(r) == 2 and r[0].split(' ')[7] == '.text':
                    adr = r[0].split(' ')[0].strip()
                    name = r[1].split(' ')[1]  # .strip();
                    # print("%s is at %s" % (name, adr))
                    self.addresses[name] = int(adr, 16)
                    self.names[int(adr, 16)] = name
            except IndexError:
                pass;
    def getadr(self,name):
        return self.addresses[name];
    def try_getadr(self,name): # DL4YHF 2017-01, used to CHECK if a symbol exists
        try:                   # to perform patches for 'optional' C functions 
            return self.addresses[name];
        except KeyError:
            return None;
    def getname(self,adr):
        return self.names[adr];

class Merger(object):
    def __init__(self, filename, offset=0x0800C000):
        """Opens the input file."""
        self.offset = offset
        self.file = open(filename, "rb")
        self.bytes = bytearray(self.file.read())
        self.length = len(self.bytes)

    def setbyte(self, adr, new, old=None):
        """Patches a single byte from the old value to the new value."""
        self.bytes[adr - self.offset] = new

    def getbyte(self, adr):
        """Reads a byte from the firmware address."""
        b = self.bytes[adr - self.offset]
        return b

    def export(self, filename):
        """Exports to a binary file."""
        outfile = open(filename, "wb")
        outfile.write(self.bytes)

    def assertbyte(self, adr, val):
        """Asserts that a byte has a given value."""
        assert self.getbyte(adr) == val
        return

    def getword(self, adr):
        """Reads a byte from the firmware address."""
        w = (
            self.bytes[adr - self.offset] +
            (self.bytes[adr - self.offset + 1] << 8) +
            (self.bytes[adr - self.offset + 2] << 16) +
            (self.bytes[adr - self.offset + 3] << 24)
        )

        return w

    def setword(self, adr, new, old=None):
        """Patches a 32-bit word from the old value to the new value."""
        if old is not None:
            self.assertbyte(adr, old & 0xFF)
            self.assertbyte(adr + 1, (old >> 8) & 0xFF)
            self.assertbyte(adr + 2, (old >> 16) & 0xFF)
            self.assertbyte(adr + 3, (old >> 24) & 0xFF)

        # print("Patching word at %08x to %08x" % (adr, new))
        self.bytes[adr - self.offset] = new & 0xFF
        self.bytes[adr - self.offset + 1] = (new >> 8) & 0xFF
        self.bytes[adr - self.offset + 2] = (new >> 16) & 0xFF
        self.bytes[adr - self.offset + 3] = (new >> 24) & 0xFF
        self.assertbyte(adr, new & 0xFF)
        self.assertbyte(adr + 1, (new >> 8) & 0xFF)

    def sethword(self, adr, new, old=None):
        """Patches a byte pair from the old value to the new value."""
        if old is not None:
            self.assertbyte(adr, old & 0xFF)
            self.assertbyte(adr + 1, (old >> 8) & 0xFF)
        # print("Patching hword at %08x to %04x" % (adr, new))
        self.bytes[adr - self.offset] = new & 0xFF
        self.bytes[adr - self.offset + 1] = (new >> 8) & 0xFF
        self.assertbyte(adr, new & 0xFF)
        self.assertbyte(adr + 1, (new >> 8) & 0xFF)

    def hookstub(self, adr, handler):
        """Hooks a function by placing an unconditional branch at adr to
           handler.  The recipient function must have an identical calling
           convention. """
        adr &= ~1  # Address must be even.
        handler |= 1  # Destination address must be odd.
        # print("Inserting a stub hook at %08x to %08x." % (adr, handler))

        # FIXME This clobbers r0, should use a different register.
        self.sethword(adr, 0x4801)  # ldr r0, [pc, 4]
        self.sethword(adr + 2, 0x4700)  # bx r0
        self.sethword(adr + 4, 0x4600)  # NOP
        self.sethword(adr + 6, 0x4600)  # NOP, might be overwritten
        if adr & 2 > 0:
            self.setword(adr + 6, handler)  # bx r0
        else:
            self.setword(adr + 8, handler)  # bx r0

    def hookstub2(self, adr, handler):
        """Hooks a function by placing an unconditional branch at adr to
           handler.  The recipient function must have an identical calling
           convention. """
        adr &= ~1  # Address must be even.
        handler |= 1  # Destination address must be odd.
        print("Inserting a stub hook at %08x to %08x." % (adr, handler))

        # insert trampoline
        # rasm2 -a arm -b 16 '<asm code>'
        self.sethword(adr, 0xb401)  # push {r0}
        self.sethword(adr + 2, 0xb401)  # push {r0}
        self.sethword(adr + 4, 0x4801)  # ldr r0, [pc, 4]
        self.sethword(adr + 6, 0x9001)  # str r0, [sp, 4] (pc)
        self.sethword(adr + 8, 0xbd01)  # pop {r0,pc}
        self.sethword(adr + 10, 0x4600)  # NOP, might be overwritten
        if adr & 2 > 0:
            self.setword(adr + 10, handler)
        else:
            self.setword(adr + 12, handler)

    def calcbl(self, adr, target):
        """Calculates the Thumb code to branch to a target."""
        offset = target - adr
        # print("offset=%08x" % offset)
        offset -= 4  # PC points to the next ins.
        offset = (offset >> 1)  # LSBit is ignored.
        hi = 0xF000 | ((offset & 0xfff800) >> 11)  # Hi address setter, but at lower adr.
        lo = 0xF800 | (offset & 0x7ff)  # Low adr setter goes next.
        # print("%04x %04x" % (hi, lo))
        word = ((lo << 16) | hi)
        # print("%08x" % word)
        return word

    def hookbl(self, adr, handler, oldhandler=None):
        """Hooks a function by replacing a 32-bit relative BL."""

        # print("Redirecting a bl at %08x to %08x." % (adr, handler))

        # TODO This is sometimes tricked by old data.
        # Fix it by ensuring no old data.
        # if oldhandler!=None:
        #    #Verify the old handler.
        #    if self.calcbl(adr,oldhandler)!=self.getword(adr):
        #        print("The old handler looks wrong.")
        #        print("Damn, we're in a tight spot!")
        #        sys.exit(1);

        self.setword(adr,
                     self.calcbl(adr, handler))


if __name__ == '__main__':
    print("Merging an applet.")
    if len(sys.argv) != 4:
        print("Usage: python merge.py firmware.img patch.img offset")
        sys.exit(1)

    # Open the firmware image.
    merger = Merger(sys.argv[1])

    # Open the applet.
    fapplet = open(sys.argv[2], "rb")
    bapplet = bytearray(fapplet.read())
    index = int(sys.argv[3], 16)

    # Open the applet symbols
    sapplet = Symbols("%s.sym" % sys.argv[2])
	
    #merger.hookstub(0x080E50C6,  # USB manufacturer string handler function.
    #                sapplet.getadr("getmfgstr"))
	
    #merger.hookbl(0x080325C2, sapplet.getadr("rx_screen_blue_hook"), 0)
    #merger.hookbl(0x0803263C, sapplet.getadr("rx_screen_blue_hook"), 0)
    #merger.hookbl(0x08028D92, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    #merger.hookbl(0x08032588, sapplet.getadr("rx_screen_blue_hook"), 0)
    #merger.hookbl(0x080325C2, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    #merger.hookbl(0x080D8A20, sapplet.getadr("usb_upld_hook"), 0x080D94BC)  # Old handler adr.
	
    # keyboard
    merger.hookbl(0x0806D73A, sapplet.getadr("kb_handler_hook"));
	
    #merger.hookbl(0x0800E4B8, sapplet.getadr("print_date_hook"), 0)
   # merger.hookbl(0x08029844, sapplet.getadr("draw_statusline_hook"))
	
    draw_datetime_row_list = [
        0x8029d4e,
        0x802a2bc,
        0x802a31a,
        0x802a414,
        0x802a47a,
        0x802a4d0,
        0x802a54c,
        0x803d548,
        0x803dd8e
    ]
    for adr in draw_datetime_row_list:
        merger.hookbl(adr, sapplet.getadr("draw_datetime_row_hook"))
	
    dmr_call_start_hook_list = [0x804c0fa, 0x804c160, 0x804c188, 0x804c730]
    for adr in dmr_call_start_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_call_start_hook"))
		
    merger.hookbl(0x0804c738, sapplet.getadr("dmr_call_end_hook"))
	
    dmr_CSBK_handler_hook_list = [0x804C3D6, 0x0804C740]
    for adr in dmr_CSBK_handler_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_CSBK_handler_hook"))
	
    merger.hookbl(0x08011664, sapplet.getadr("f_1444_hook"))
	
    dmr_handle_data_hook_list = [0x804c76c, 0x804c776, 0x804c7d4]
    for adr in dmr_handle_data_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_handle_data_hook"))
				  
    drwbmplist = [
        0x800d18c,
        0x800eda4,
        0x800edb2,
        0x800edce,
        0x800eddc,
        0x800ee5a,
        0x800ee68,
        0x800ee84,
        0x800ee92,
        0x800eeee,
        0x800ef1a,
        0x800ef46,
        0x800ef72,
        0x800ef9e,
        0x800efca,
        0x800f084,
        0x800f092,
        0x800f0e2,
        0x800f15c,
        0x800f16a,
        0x800f1ba,
        0x80290e2,
        0x802a64a,
        0x802a658,
        0x802ab90,
        0x802ab9c,
        0x80330b6,
        0x80330e4,
        0x80330f0,
        0x8033114,
        0x8033152,
        0x803316a,
        0x80359e6,
        0x8035a1c,
        0x8035a46,
        0x8035a70,
        0x8035a8e,
        0x8035b66,
        0x8035bb2,
        0x8035bd6,
        0x8035c30,
        0x8035c44,
        0x8035cb2,
        0x8035cc6,
        0x8035cfe,
        0x8035d3c,
        0x8035d9c,
        0x8035dde,
        0x8035eaa,
        0x80399ea,
        0x8039a94,
        0x8039b7c,
        0x8039ce2,
        0x8039d76,
        0x8039e8e,
        0x8039f72,
        0x8039ffc,
        0x803a150,
        0x803a15c,
        0x803a27e,
        0x803a30a,
        0x803a3fa,
        0x803a460,
        0x803a4de,
        0x803b05c,
        0x8047a18,
        0x8047a40,
        0x8047a94,
        0x8047ad0,
        0x8053470,
        0x80534a2,
        0x80646d4,
        0x806b0cc
    ]
    for adr in drwbmplist:
        merger.hookbl(adr, sapplet.getadr("gfx_drawbmp_hook"))
		
    gfxblockfill = [
        0x800caa2,
        0x800caae,
        0x800caba,
        0x800cac6,
        0x800cada,
        0x800cae6,
        0x800caf2,
        0x800cafe,
        0x800cb0a,
        0x800cb24,
        0x800cb4a,
        0x800cb56,
        0x800cb6a,
        0x800cc4a,
        0x800cc56,
        0x800cc62,
        0x800cc74,
        0x800cc92,
        0x800cc9e,
        0x800ccb2,
        0x800cd48,
        0x800cd54,
        0x800cd60,
        0x800cdd8,
        0x800cde4,
        0x800cdf0,
        0x800cdfc,
        0x800ce10,
        0x800ce1c,
        0x800ce30,
        0x800ce3c,
        0x800ce50,
        0x800cec6,
        0x800cf7c,
        0x800d3ce,
        0x800d400,
        0x800d5c0,
        0x800d5cc,
        0x800d630,
        0x800d75e,
        0x800d76a,
        0x800d776,
        0x800d782,
        0x800d890,
        0x800d89c,
        0x800d8a8,
        0x800d8b4,
        0x800d980,
        0x800da06,
        0x800da12,
        0x800da1e,
        0x800da2a,
        0x800dcbe,
        0x800de06,
        0x800de20,
        0x800de2c,
        0x800de7c,
        0x800de88,
        0x800de94,
        0x800e170,
        0x800e3ce,
        0x800e3e2,
        0x800e3ee,
        0x800e3fa,
        0x800e406,
        0x800e6b0,
        0x800e732,
        0x800e740,
        0x800e74c,
        0x800e758,
        0x800e76e,
        0x800e83e,
        0x800e8aa,
        0x800e8d2,
        0x800ea6c,
        0x800ea80,
        0x800ea8c,
        0x800ea98,
        0x800eaa4,
        0x800ee1a,
        0x800ee28,
        0x800efe0,
        0x800f0f8,
        0x800f1d0,
        0x800f23a,
        0x800f248,
        0x800f348,
        0x800f432,
        0x800f52a,
        0x800f85c,
        0x800f876,
        0x800f8b4,
        0x800f8c0,
        0x800f8cc,
        0x800f8de,
        0x800f8f2,
        0x800f8fe,
        0x800f9c8,
        0x800f9ec,
        0x800fa06,
        0x800fa28,
        0x800fa42,
        0x8026e5e,
        0x8026e6c,
        0x8026e7c,
        0x802706e,
        0x802707e,
        0x8028b90,
        0x80293e2,
        0x8029638,
        0x802981e,
        0x8029886,
        0x8029f54,
        0x802a17e,
        0x802a2a2,
        0x802a2d0,
        0x802a32a,
        0x802a336,
        0x802a342,
        0x802a34e,
        0x802a35a,
        0x802a366,
        0x802a3fa,
        0x802a428,
        0x802a48e,
        0x802a4e4,
        0x802a55c,
        0x802a568,
        0x802a574,
        0x802a580,
        0x802a58c,
        0x802a598,
        0x8031ee8,
        0x8031ef4,
        0x8031f00,
        0x8031f12,
        0x8031f1e,
        0x80328fc,
        0x8032908,
        0x803299a,
        0x8032a24,
        0x8032ac6,
        0x8032ba0,
        0x8032c6a,
        0x8032d4a,
        0x8032d56,
        0x8032e0a,
        0x8032e16,
        0x8032f7a,
        0x8033004,
        0x803301e,
        0x803307a,
        0x8033086,
        0x8033092,
        0x8033136,
        0x8033186,
        0x8033192,
        0x8033234,
        0x8038ecc,
        0x8038ee0,
        0x8039e08,
        0x8039f5c,
        0x803a294,
        0x803a366,
        0x803a454,
        0x803a7d0,
        0x803a848,
        0x803abe6,
        0x803bb4c,
        0x803bc34,
        0x803bc46,
        0x803bc52,
        0x803bc66,
        0x803bc72,
        0x803d396,
        0x803d3a2,
        0x803d3ae,
        0x803d3fc,
        0x803d408,
        0x803d414,
        0x803d420,
        0x803d42c,
        0x803d438,
        0x803d444,
        0x803d538,
        0x803d544,
        0x803d55c,
        0x803d570,
        0x803d57c,
        0x803d588,
        0x803d696,
        0x803d6a2,
        0x803d6ae,
        0x803d6c2,
        0x803d6ce,
        0x803d6da,
        0x803d6e6,
        0x803d6f2,
        0x803d6fe,
        0x803d73c,
        0x803d748,
        0x803d7ca,
        0x803d7d6,
        0x803d808,
        0x803d828,
        0x803d834,
        0x803d864,
        0x803d870,
        0x803d8a8,
        0x803d8d8,
        0x803d8e4,
        0x803d91c,
        0x803d95e,
        0x803d9a2,
        0x803d9e2,
        0x803da26,
        0x803da32,
        0x803da64,
        0x803da84,
        0x803da90,
        0x803dac0,
        0x803dacc,
        0x803db04,
        0x803db34,
        0x803db40,
        0x803db78,
        0x803dbba,
        0x803dbfe,
        0x803dc3c,
        0x803dc76,
        0x803dc98,
        0x803dca4,
        0x803dcb0,
        0x803dcbe,
        0x803dcca,
        0x803dcd8,
        0x803dcfa,
        0x803dd08,
        0x803dd14,
        0x803dd20,
        0x803dd38,
        0x803dd7e,
        0x803dd8a,
        0x803e824,
        0x803e830,
        0x803e928,
        0x803e936,
        0x803f3d8,
        0x803f3e4,
        0x8047a60,
        0x8047abe,
        0x805155a,
        0x805157a,
        0x806c354
    ]
    for adr in gfxblockfill:
        merger.hookbl(adr, sapplet.getadr("gfx_blockfill_hook"))
		
    #dt2list = [
    #    0x0800CBA0,
    #    0x0800CBC2,
    #    0x0800CCE8,
    #    0x0800CE86,
    #    0x0800CEA8,
    #    0x0800CF82,
    #    0x0800CFCE,
    #    0x0800D08C,
    #    0x0800D0D8,
    #    0x0800D166,
    #    0x0800D1B6,
    #    0x0800D2E2,
    #    0x0800D3E0,
    #    0x0800D48E,
    #    0x0800D7BC,
    #    0x0800E826,
    #    0x0800E846,
    #    0x0800F74A,
    #    0x0800F7D8,
    #    0x0800F7F8,
    #    0x08027922,
    #    0x08027A2A,
    #    0x080284B0,
    #    0x080284CE,
    #    0x0802872C,
    #    0x08028782,
    #    0x08029576,
    #    0x080295C2,
    #    0x080295F6,
    #    0x08029636,
    #    0x08029686,
    #    0x08029698,
    #    0x080296D8,
    #    0x08030AD6,
    #    0x08030B04,
    #    0x08030B58,
    #    0x08030C74,
    #    0x08030EA4,
    #    0x08038724,
    #    0x08039790,
    #    0x080397B0,
    #    0x08063488,
    #    0x080634A8,
    #]
    #for adr in dt2list:
    #    merger.hookbl(adr, sapplet.getadr("gfx_drawtext10_hook"))
		
    dt4list = [
        0x800f334,
        0x800f36e,
        0x800f3de,
        0x800f41e,
        0x800f4a8,
        0x800f4e8,
        0x800f516,
        0x800f55c,
        0x800f5ca,
        0x8032cd2,
        0x8032d2e
    ]
    for adr in dt4list:
        merger.hookbl(adr, sapplet.getadr("gfx_drawtext4_hook"))

    gfxdrawcharpos = [
        0x800d0e8,
        0x800d134,
        0x800d1f2,
        0x800d23e,
        0x800d2c8,
        0x800d316,
        0x800d3e6,
        0x800d488,
        0x800d4f6,
        0x800dd38,
        0x80320be,
        0x80320d6,
        0x80320ea,
        0x8032102,
        0x8033036,
        0x8033040,
        0x803305a,
        0x8033066,
        0x803d48c,
        0x803d4b0,
        0x803d4cc,
        0x803d4e6,
        0x803d508,
        0x803d524,
        0x803d7e6,
        0x803d84c,
        0x803d88e,
        0x803d8ca,
        0x803d902,
        0x803d944,
        0x803d980,
        0x803da42,
        0x803daa8,
        0x803daea,
        0x803db26,
        0x803db5e,
        0x803dba0,
        0x803dbdc,
    ]
    for adr in gfxdrawcharpos:
        merger.hookbl(adr, sapplet.getadr("gfx_drawchar_pos_hook"))
    
    gfxdt10 = [
        0x800cb36,
        0x800cd20,
        0x800cf60,
        0x800d0b2,
        0x800d0d0,
        0x800d11c,
        0x800d1bc,
        0x800d1da,
        0x800d226,
        0x800d292,
        0x800d2b0,
        0x800d2fe,
        0x800d418,
        0x800d428,
        0x800d4bc,
        0x800d52a,
        0x800d61c,
        0x800d65e,
        0x800d67c,
        0x800d6c6,
        0x800dd98,
        0x800ddb6,
        0x800de5e,
        0x800deba,
        0x800ded8,
        0x800e610,
        0x800e68a,
        0x800e882,
        0x800e89e,
        0x800e8c6,
        0x800e8ee,
        0x800f9b4,
        0x80272c0,
        0x8027a8a,
        0x8027aa2,
        0x8027ad8,
        0x8027af0,
        0x8032986,
        0x8032b8c,
        0x8032bfc,
        0x8032c4e,
        0x8032dc4,
        0x803d3da,
        0x803d71a,
    ]
    for adr in gfxdt10:
        merger.hookbl(adr, sapplet.getadr("gfx_drawtext2_hook"))
	
    rxscrn_hooks = [
        0x80290c0,
        0x8032df4,
        0x803b03a
    ]
    for adr in rxscrn_hooks:
        merger.hookbl(adr, sapplet.getadr("rx_screen_blue_hook"))
		
	# f_4315
    merger.hookbl(0x08028F50, sapplet.getadr("f_4315_hook"))
    merger.hookbl(0x08028F86, sapplet.getadr("f_4315_hook"))
	
    merger.hookbl(0x0803DEC8, sapplet.getadr("f_4225_hook"), 0)
    merger.hookbl(0x08064834, sapplet.getadr("f_4225_hook"), 0)

    merger.hookbl(0x801AC40, sapplet.getadr("sub_801AC40"), 0)
	
    merger.hookbl(0x080154AE, sapplet.getadr("create_menu_utilies_hook"), 0)
	
    spiflashreadhooks = [
        0x8013520,
        0x80258fc,
        0x8025b5e,
        0x802c72e,
        0x802c740,
        0x802c752,
        0x802c764,
        0x802c7a0,
        0x802ca0c,
        0x802ca2c,
        0x802ca52,
        0x802ca96,
        0x802cb4c,
        0x802cb56,
        0x802cbcc,
        0x802cbf8,
        0x802cc2c,
        0x8033482,
        0x8033534,
        0x8033572,
        0x804150a,
        0x80415e2,
        0x804397a,
        0x80439dc,
        0x8043a30,
        0x8043a76,
        0x8043ab4,
        0x8043b38,
        0x8043bae
    ]
    for adr in spiflashreadhooks:
        merger.hookbl(adr, sapplet.getadr("spiflash_read_hook"))
	
    print("Merging %s into %s at %08x" % (
        sys.argv[2],
        sys.argv[1],
        index))

    i = 0
    for b in bapplet:
        merger.setbyte(index + i, bapplet[i])
        i += 1

    merger.export(sys.argv[1])
