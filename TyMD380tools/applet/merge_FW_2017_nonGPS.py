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
	
    merger.hookbl(0x080325A8, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x08032622, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x08028804, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    merger.hookbl(0x0803256E, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x080325CC, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    #merger.hookbl(0x080D8A20, sapplet.getadr("usb_upld_hook"), 0x080D94BC)  # Old handler adr.
	
    # keyboard
    merger.hookbl(0x0806C47E, sapplet.getadr("kb_handler_hook"));
	
    #merger.hookbl(0x0800E4B8, sapplet.getadr("print_date_hook"), 0)
   # merger.hookbl(0x08029844, sapplet.getadr("draw_statusline_hook"))
	
    draw_datetime_row_list = [
        0x8029278,
        0x80297f0,
        0x8029856,
        0x8029954,
        0x80299b8,
        0x8029a0a,
        0x8029a76,
        0x803c8cc,
        0x803d10a
    ]
    for adr in draw_datetime_row_list:
        merger.hookbl(adr, sapplet.getadr("draw_datetime_row_hook"))
	
    dmr_call_start_hook_list = [0x0804AB9A, 0x0804AC00, 0x0804AC28, 0x0804B1D0]
    for adr in dmr_call_start_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_call_start_hook"))
		
    merger.hookbl(0x0804B1D8, sapplet.getadr("dmr_call_end_hook"))
	
    merger.hookbl(0x0804AE76, sapplet.getadr("dmr_CSBK_handler_hook"))
    merger.hookbl(0x0804B1E0, sapplet.getadr("dmr_CSBK_handler_hook"))
	
    merger.hookbl(0x08011664, sapplet.getadr("f_1444_hook"))
	
    dmr_handle_data_hook_list = [0x0804B20C, 0x0804B216, 0x0804B274]
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
        0x8028804,
        0x8029b64,
        0x8029b72,
        0x802a03a,
        0x802a046,
        0x803256e,
        0x803259c,
        0x80325a8,
        0x80325cc,
        0x803260a,
        0x8032622,
        0x8034e9e,
        0x8034ed4,
        0x8034efe,
        0x8034f28,
        0x8034f46,
        0x803501e,
        0x803506a,
        0x803508e,
        0x80350e8,
        0x80350fc,
        0x803516a,
        0x803517e,
        0x80351b6,
        0x80351f4,
        0x8035254,
        0x8035296,
        0x8035362,
        0x8038ea2,
        0x8038f4c,
        0x8039034,
        0x803919a,
        0x803922e,
        0x8039346,
        0x803942a,
        0x80394b4,
        0x8039608,
        0x8039614,
        0x8039736,
        0x80397c2,
        0x80398b2,
        0x8039918,
        0x8039996,
        0x803a518,
        0x80464b8,
        0x80464e0,
        0x8046534,
        0x8046570,
        0x8051f5c,
        0x8051f8e,
        0x8063024,
        0x806998c
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
        0x80265ea,
        0x80265f8,
        0x8026608,
        0x80267fa,
        0x802680a,
        0x802831c,
        0x8028aae,
        0x8028cfe,
        0x802947c,
        0x80296ae,
        0x80297d4,
        0x8029802,
        0x8029866,
        0x8029872,
        0x802987e,
        0x802988a,
        0x8029896,
        0x80298a2,
        0x8029938,
        0x8029966,
        0x80299ca,
        0x8029a1c,
        0x8029a86,
        0x8029a92,
        0x8029a9e,
        0x8029aaa,
        0x8029ab6,
        0x8029ac2,
        0x80313a0,
        0x80313ac,
        0x80313b8,
        0x80313ca,
        0x80313d6,
        0x8031db4,
        0x8031dc0,
        0x8031e52,
        0x8031edc,
        0x8031f7e,
        0x8032058,
        0x8032122,
        0x8032202,
        0x803220e,
        0x80322c2,
        0x80322ce,
        0x8032432,
        0x80324bc,
        0x80324d6,
        0x8032532,
        0x803253e,
        0x803254a,
        0x80325ee,
        0x803263e,
        0x803264a,
        0x80326ec,
        0x8038384,
        0x8038398,
        0x80392c0,
        0x8039414,
        0x803974c,
        0x803981e,
        0x803990c,
        0x8039c88,
        0x8039d00,
        0x803a0a2,
        0x803b008,
        0x803b01a,
        0x803b026,
        0x803b03a,
        0x803b046,
        0x803c71a,
        0x803c726,
        0x803c732,
        0x803c780,
        0x803c78c,
        0x803c798,
        0x803c7a4,
        0x803c7b0,
        0x803c7bc,
        0x803c7c8,
        0x803c8bc,
        0x803c8c8,
        0x803c8e0,
        0x803c8f4,
        0x803c900,
        0x803c90c,
        0x803ca12,
        0x803ca1e,
        0x803ca2a,
        0x803ca3e,
        0x803ca4a,
        0x803ca56,
        0x803ca62,
        0x803ca6e,
        0x803ca7a,
        0x803cab8,
        0x803cac4,
        0x803cb46,
        0x803cb52,
        0x803cb84,
        0x803cba4,
        0x803cbb0,
        0x803cbe0,
        0x803cbec,
        0x803cc24,
        0x803cc54,
        0x803cc60,
        0x803cc98,
        0x803ccda,
        0x803cd1e,
        0x803cd5e,
        0x803cda2,
        0x803cdae,
        0x803cde0,
        0x803ce00,
        0x803ce0c,
        0x803ce3c,
        0x803ce48,
        0x803ce80,
        0x803ceb0,
        0x803cebc,
        0x803cef4,
        0x803cf36,
        0x803cf7a,
        0x803cfb8,
        0x803cff2,
        0x803d014,
        0x803d020,
        0x803d02c,
        0x803d03a,
        0x803d046,
        0x803d054,
        0x803d076,
        0x803d084,
        0x803d090,
        0x803d09c,
        0x803d0b4,
        0x803d0fa,
        0x803d106,
        0x803dae0,
        0x803daec,
        0x803dbe4,
        0x803dbf2,
        0x803e6d0,
        0x803e6dc,
        0x8046500,
        0x804655e,
        0x8050046,
        0x8050066,
        0x806b0a8
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
        0x803218a,
        0x80321e6
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
        0x8031576,
        0x803158e,
        0x80315a2,
        0x80315ba,
        0x80324ee,
        0x80324f8,
        0x8032512,
        0x803251e,
        0x803c810,
        0x803c834,
        0x803c850,
        0x803c86a,
        0x803c88c,
        0x803c8a8,
        0x803cb62,
        0x803cbc8,
        0x803cc0a,
        0x803cc46,
        0x803cc7e,
        0x803ccc0,
        0x803ccfc,
        0x803cdbe,
        0x803ce24,
        0x803ce66,
        0x803cea2,
        0x803ceda,
        0x803cf1c,
        0x803cf58,
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
        0x8026a4c,
        0x8027216,
        0x802722e,
        0x8027264,
        0x802727c,
        0x8031e3e,
        0x8032044,
        0x80320b4,
        0x8032106,
        0x803227c,
        0x803c75e,
        0x803ca96
    ]
    for adr in gfxdt10:
        merger.hookbl(adr, sapplet.getadr("gfx_drawtext2_hook"))
	
	# f_4315
    merger.hookbl(0x080286B0, sapplet.getadr("f_4315_hook"))
    merger.hookbl(0x080286E6, sapplet.getadr("f_4315_hook"))
	
    merger.hookbl(0x0803D24C, sapplet.getadr("f_4225_hook"), 0)
    merger.hookbl(0x0806313E, sapplet.getadr("f_4225_hook"), 0)
	
    print("Merging %s into %s at %08x" % (
        sys.argv[2],
        sys.argv[1],
        index))

    i = 0
    for b in bapplet:
        merger.setbyte(index + i, bapplet[i])
        i += 1

    merger.export(sys.argv[1])
