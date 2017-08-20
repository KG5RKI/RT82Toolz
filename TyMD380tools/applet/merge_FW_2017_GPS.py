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
	
    merger.hookbl(0x080325C2, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x0803263C, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x08028D92, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    merger.hookbl(0x08032588, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x080325C2, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    #merger.hookbl(0x080D8A20, sapplet.getadr("usb_upld_hook"), 0x080D94BC)  # Old handler adr.
	
    # keyboard
    merger.hookbl(0x0806F9B2, sapplet.getadr("kb_handler_hook"));
	
    #merger.hookbl(0x0800E4B8, sapplet.getadr("print_date_hook"), 0)
   # merger.hookbl(0x08029844, sapplet.getadr("draw_statusline_hook"))
	
    draw_datetime_row_list = [
        0x8029a3e,
        0x8029fe2,
        0x802a04a,
        0x802a14a,
        0x802a1b6,
        0x802a212,
        0x802a284,
        0x803c9c8,
        0x803d20e,
    ]
    for adr in draw_datetime_row_list:
        merger.hookbl(adr, sapplet.getadr("draw_datetime_row_hook"))
	
    dmr_call_start_hook_list = [0x804e532,0x804e598,0x804e5c0,0x804eb68]
    for adr in dmr_call_start_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_call_start_hook"))
		
    merger.hookbl(0x0804EB70, sapplet.getadr("dmr_call_end_hook"))
	
    dmr_CSBK_handler_hook_list = [0x804e80e, 0x804eb78]
    for adr in dmr_CSBK_handler_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_CSBK_handler_hook"))
	
    merger.hookbl(0x08011460, sapplet.getadr("f_1444_hook"))
	
    dmr_handle_data_hook_list = [0x804eba4, 0x804ebae, 0x804ec0c,]
    for adr in dmr_handle_data_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_handle_data_hook"))
				  
    drwbmplist = [
        0x800d010,
        0x800ec48,
        0x800ec56,
        0x800ec72,
        0x800ec80,
        0x800ecfe,
        0x800ed0c,
        0x800ed28,
        0x800ed36,
        0x800ed92,
        0x800edbe,
        0x800edea,
        0x800ee16,
        0x800ee42,
        0x800ee6e,
        0x800ef28,
        0x800ef36,
        0x800ef86,
        0x800f000,
        0x800f00e,
        0x800f05e,
        0x8028d92,
        0x802a384,
        0x802a392,
        0x802a8fc,
        0x802a908,
        0x8032588,
        0x80325b6,
        0x80325c2,
        0x80325e6,
        0x8032624,
        0x803263c,
        0x8034ed8,
        0x8034f0e,
        0x8034f38,
        0x8034f62,
        0x8034f80,
        0x8035058,
        0x80350a0,
        0x80350c4,
        0x8035122,
        0x8035136,
        0x80351a8,
        0x80351bc,
        0x80351f4,
        0x8035232,
        0x8035296,
        0x80352d8,
        0x8035374,
        0x8038e22,
        0x8038ecc,
        0x8038fb4,
        0x803911a,
        0x80391ae,
        0x80392c6,
        0x80393aa,
        0x8039434,
        0x8039588,
        0x8039594,
        0x80396b6,
        0x8039742,
        0x8039832,
        0x8039898,
        0x8039916,
        0x803a47e,
        0x8049a8c,
        0x8049ab4,
        0x8049b08,
        0x8049b44,
        0x80558b0,
        0x80558e2,
        0x806693c,
        0x806d344,
    ]
    for adr in drwbmplist:
        merger.hookbl(adr, sapplet.getadr("gfx_drawbmp_hook"))
		
    gfxblockfill = [
        0x800caa6,
        0x800cab2,
        0x800cabe,
        0x800caca,
        0x800cade,
        0x800caea,
        0x800caf6,
        0x800cb02,
        0x800cb0e,
        0x800cb28,
        0x800cb4e,
        0x800cb5a,
        0x800cb6e,
        0x800cc4e,
        0x800cc5a,
        0x800cc66,
        0x800cc78,
        0x800cc96,
        0x800cca2,
        0x800ccb6,
        0x800cd4c,
        0x800cd58,
        0x800cd64,
        0x800cddc,
        0x800cde8,
        0x800cdf4,
        0x800ce00,
        0x800ce14,
        0x800ce20,
        0x800ce34,
        0x800ce40,
        0x800ce54,
        0x800ceca,
        0x800d258,
        0x800d28a,
        0x800d450,
        0x800d45c,
        0x800d4c0,
        0x800d5ec,
        0x800d5f8,
        0x800d604,
        0x800d610,
        0x800d722,
        0x800d72e,
        0x800d73a,
        0x800d746,
        0x800d7fa,
        0x800d87a,
        0x800d886,
        0x800d892,
        0x800d89e,
        0x800db3a,
        0x800dc82,
        0x800dc9c,
        0x800dca8,
        0x800dcf8,
        0x800dd04,
        0x800dd10,
        0x800dff2,
        0x800e27e,
        0x800e292,
        0x800e29e,
        0x800e2aa,
        0x800e2b6,
        0x800e558,
        0x800e5ce,
        0x800e5dc,
        0x800e5e8,
        0x800e5f4,
        0x800e608,
        0x800e6e2,
        0x800e74c,
        0x800e774,
        0x800e90c,
        0x800e920,
        0x800e92c,
        0x800e938,
        0x800e944,
        0x800ecbe,
        0x800eccc,
        0x800ee84,
        0x800ef9c,
        0x800f074,
        0x800f0de,
        0x800f0ec,
        0x800f1e4,
        0x800f2ce,
        0x800f3c6,
        0x800f700,
        0x800f71a,
        0x800f75c,
        0x800f768,
        0x800f774,
        0x800f786,
        0x800f79a,
        0x800f7a6,
        0x800f878,
        0x800f89c,
        0x800f8b6,
        0x800f8d8,
        0x800f8f2,
        0x80269fa,
        0x8026a08,
        0x8026a18,
        0x8026c0a,
        0x8026c1a,
        0x80287a6,
        0x802908c,
        0x8029306,
        0x802950e,
        0x802956c,
        0x8029c68,
        0x8029e9a,
        0x8029fc6,
        0x8029ff6,
        0x802a05a,
        0x802a066,
        0x802a072,
        0x802a07e,
        0x802a08a,
        0x802a096,
        0x802a12e,
        0x802a15e,
        0x802a1ca,
        0x802a226,
        0x802a294,
        0x802a2a0,
        0x802a2ac,
        0x802a2b8,
        0x802a2c4,
        0x802a2d0,
        0x8031df0,
        0x8031dfc,
        0x8031e8e,
        0x8031f18,
        0x8031fba,
        0x8032094,
        0x803215e,
        0x803223e,
        0x803224a,
        0x80322dc,
        0x80322e8,
        0x803244c,
        0x80324d6,
        0x80324f0,
        0x803254c,
        0x8032558,
        0x8032564,
        0x8032608,
        0x8032658,
        0x8032664,
        0x8032706,
        0x8038304,
        0x8038318,
        0x8039240,
        0x8039394,
        0x80396cc,
        0x803979e,
        0x803988c,
        0x8039c08,
        0x8039c80,
        0x803a01e,
        0x803af6e,
        0x803b050,
        0x803b062,
        0x803b06e,
        0x803b082,
        0x803b08e,
        0x803c816,
        0x803c822,
        0x803c82e,
        0x803c87c,
        0x803c888,
        0x803c894,
        0x803c8a0,
        0x803c8ac,
        0x803c8b8,
        0x803c8c4,
        0x803c9b8,
        0x803c9c4,
        0x803c9dc,
        0x803c9f0,
        0x803c9fc,
        0x803ca08,
        0x803cb16,
        0x803cb22,
        0x803cb2e,
        0x803cb42,
        0x803cb4e,
        0x803cb5a,
        0x803cb66,
        0x803cb72,
        0x803cb7e,
        0x803cbbc,
        0x803cbc8,
        0x803cc4a,
        0x803cc56,
        0x803cc88,
        0x803cca8,
        0x803ccb4,
        0x803cce4,
        0x803ccf0,
        0x803cd28,
        0x803cd58,
        0x803cd64,
        0x803cd9c,
        0x803cdde,
        0x803ce22,
        0x803ce62,
        0x803cea6,
        0x803ceb2,
        0x803cee4,
        0x803cf04,
        0x803cf10,
        0x803cf40,
        0x803cf4c,
        0x803cf84,
        0x803cfb4,
        0x803cfc0,
        0x803cff8,
        0x803d03a,
        0x803d07e,
        0x803d0bc,
        0x803d0f6,
        0x803d118,
        0x803d124,
        0x803d130,
        0x803d13e,
        0x803d14a,
        0x803d158,
        0x803d17a,
        0x803d188,
        0x803d194,
        0x803d1a0,
        0x803d1b8,
        0x803d1fe,
        0x803d20a,
        0x803dca4,
        0x803dcb0,
        0x803dda8,
        0x803ddb6,
        0x803e858,
        0x803e864,
        0x8049ad4,
        0x8049b32,
        0x8053986,
        0x80539a6,
        0x806e5cc,
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
        0x800f1d0,
        0x800f20a,
        0x800f27a,
        0x800f2ba,
        0x800f344,
        0x800f384,
        0x800f3b2,
        0x800f3f8,
        0x800f466,
        0x80321c6,
        0x8032222,
    ]
    for adr in dt4list:
        merger.hookbl(adr, sapplet.getadr("gfx_drawtext4_hook"))

    gfxdrawcharpos = [
        0x800cf6c,
        0x800cfb8,
        0x800d076,
        0x800d0c2,
        0x800d14c,
        0x800d19c,
        0x800d270,
        0x800d316,
        0x800d386,
        0x800dbb4,
        0x8032508,
        0x8032512,
        0x803252c,
        0x8032538,
        0x803c90c,
        0x803c930,
        0x803c94c,
        0x803c966,
        0x803c988,
        0x803c9a4,
        0x803cc66,
        0x803cccc,
        0x803cd0e,
        0x803cd4a,
        0x803cd82,
        0x803cdc4,
        0x803ce00,
        0x803cec2,
        0x803cf28,
        0x803cf6a,
        0x803cfa6,
        0x803cfde,
        0x803d020,
        0x803d05c,
    ]
    for adr in gfxdrawcharpos:
        merger.hookbl(adr, sapplet.getadr("gfx_drawchar_pos_hook"))
    
    gfxdt10 = [
        0x800cb3a,
        0x800cd24,
        0x800cf36,
        0x800cf54,
        0x800cfa0,
        0x800d040,
        0x800d05e,
        0x800d0aa,
        0x800d116,
        0x800d134,
        0x800d184,
        0x800d2a2,
        0x800d2b4,
        0x800d34c,
        0x800d3bc,
        0x800d4ac,
        0x800d4e6,
        0x800d504,
        0x800d554,
        0x800dc14,
        0x800dc32,
        0x800dcda,
        0x800dd36,
        0x800dd54,
        0x800e4b8,
        0x800e532,
        0x800e724,
        0x800e740,
        0x800e768,
        0x800e790,
        0x800f864,
        0x8026e5c,
        0x8027626,
        0x802763e,
        0x8027674,
        0x802768c,
        0x8031e7a,
        0x8032080,
        0x80320f0,
        0x8032142,
        0x80322b8,
        0x803c85a,
        0x803cb9a,
    ]
    for adr in gfxdt10:
        merger.hookbl(adr, sapplet.getadr("gfx_drawtext2_hook"))
	
	# f_4315
    merger.hookbl(0x08028C14, sapplet.getadr("f_4315_hook"))
    merger.hookbl(0x08028C4A, sapplet.getadr("f_4315_hook"))
	
    merger.hookbl(0x0803D348, sapplet.getadr("f_4225_hook"), 0)
    merger.hookbl(0x08066A9C, sapplet.getadr("f_4225_hook"), 0)
	
    print("Merging %s into %s at %08x" % (
        sys.argv[2],
        sys.argv[1],
        index))

    i = 0
    for b in bapplet:
        merger.setbyte(index + i, bapplet[i])
        i += 1

    merger.export(sys.argv[1])
