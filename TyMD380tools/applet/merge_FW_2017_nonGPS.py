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
	
    #merger.hookbl(0x080D10BD, sapplet.getadr("usb_upld_hook"), 0)  # Old handler adr.
	
    # keyboard
    merger.hookbl(0x0806C47E, sapplet.getadr("kb_handler_hook"));
	
    #merger.hookbl(0x0800E4B8, sapplet.getadr("print_date_hook"), 0)
   # merger.hookbl(0x08029844, sapplet.getadr("draw_statusline_hook"))

    mbx_pend_list = [
        0x08040C9E,
        0x0805675E,
        0x080573AA,
        0x080578C6,
        0x080596BE,
        0x080635B2,
        0x80635D8,
    ]
    for adr in mbx_pend_list:
        merger.hookbl(adr, sapplet.getadr("OSMboxPend_hook"))
   
    
    merger.hookbl(0x08062A08, sapplet.getadr("init_global_addl_config_hook"), 0)
	
    dmr_before_squelch_list = [
        0x804b446,
        0x804b48e,
        0x804b4ce,
        0x804b524,
        0x804b5bc,
        0x804b69e,
        0x804b72a,
        0x804b782,
        0x804b7fe,
    ]
    #for adr in dmr_before_squelch_list:
    #    merger.hookbl(adr, sapplet.getadr("dmr_before_squelch_hook"))
	
    aes_cipher_hook_list = [0x0802BB6E, 0x0802C4E0]
    for adr in aes_cipher_hook_list:
        merger.hookbl(adr, sapplet.getadr("aes_cipher_hook"))
	
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
	
    rxscrn_hooks = [
        #0x80287e2,
        0x80322ac,
    ]
    for adr in rxscrn_hooks:
        merger.hookbl(adr, sapplet.getadr("rx_screen_blue_hook"))
		
    rxscrn_hooks = [
        0x0803a4f6,
        0x080287E2,
    ]
    for adr in rxscrn_hooks:
        merger.hookbl(adr, sapplet.getadr("rx_screen_gray_hook"))
		
		
    GetContactIDFromIndex_hooks = [
        0x802bf5c,
        0x802bf8c,
        0x802bfb8,
        0x802e0ee,
    ]
    #for adr in GetContactIDFromIndex_hooks:
        #merger.hookbl(adr, sapplet.getadr("read_contact_hook"))
    
    merger.hookstub2(0x0800C93C, sapplet.getadr("create_menu_entry_rev"))
	
	# f_4315
    merger.hookbl(0x080286B0, sapplet.getadr("f_4315_hook"))
    merger.hookbl(0x080286E6, sapplet.getadr("f_4315_hook"))
	
    merger.hookbl(0x0803D24C, sapplet.getadr("f_4225_hook"), 0)
    merger.hookbl(0x0806313E, sapplet.getadr("f_4225_hook"), 0)
	
    #merger.hookbl(0x0801A5BC, sapplet.getadr("sub_801AC40"), 0)
    
	
    merger.hookbl(0x08015416, sapplet.getadr("create_menu_utilies_hook"), 0)
	
	#0801532E #sets up utilities
    
    spiflashreadhooks = [
        0x801348c,
        0x802bbd2,
        0x802bbe4,
        0x802bbf6,
        0x802bc08,
        0x802bc44,
        0x802beb0,
        0x802bed0,
        0x802bef6,
        0x802bf3a,
        0x802bff0,
        0x802bffa,
        0x802c070,
        0x802c09c,
        0x802c0d0,
        0x802cafe,
        0x8032a2a,
        0x80407ee,
        0x80408c6,
        0x8042c5e,
        0x8042cc0,
        0x8042d14,
        0x8042d5a,
        0x8045eea,
    ]
    #for adr in spiflashreadhooks:
    #    merger.hookbl(adr, sapplet.getadr("spiflash_read_hook"))
	
    md380_create_menu_entry_hooks = [
        0x800c276,
        0x800c2fe,
        0x800c332,
        0x800c3a4,
        0x800c3d8,
        0x800c40a,
        0x800c43c,
        0x800c46e,
        0x800c4a2,
        0x800c550,
        0x800c5d8,
        0x800c60c,
        0x800c67e,
        0x800c6b0,
        0x800c6da,
        0x800c702,
        0x800c72a,
        0x800c754,
        0x800c7ce,
        0x800c7f6,
        0x800c82a,
        0x800c854,
        0x800c87c,
        0x800c8a4,
        0x800c8cc,
        0x800c8f6,
        0x800f700,
        0x800f724,
        0x80116ee,
        0x8011720,
        0x801176c,
        0x80117a0,
        0x801181e,
        0x80118d4,
        0x801191c,
        0x8011bd6,
        0x8011c22,
        0x8011d74,
        0x8011da6,
        0x8011dd8,
        0x8011e0a,
        0x8011e3c,
        0x8011e6e,
        0x8011ea0,
        0x8011ed2,
        0x8011fae,
        0x801204e,
        0x8012160,
        0x8012242,
        0x801236c,
        0x801249c,
        0x80124ca,
        0x801254a,
        0x8012578,
        0x80125f4,
        0x8012a40,
        0x8012a72,
        0x8012ace,
        0x8012b00,
        0x8012b32,
        0x8012b8c,
        0x8012bd6,
        0x8012c0a,
        0x8012c56,
        0x8012ca2,
        0x8012cee,
        0x8012d3a,
        0x8012d6e,
        0x8012dde,
        0x8012e32,
        0x8012e7c,
        0x8012edc,
        0x8012fa6,
        0x8013052,
        0x80130e0,
        0x801317a,
        0x80137de,
        0x80138c2,
        0x8013a88,
        0x8013d26,
        0x8013d9c,
        0x8013e34,
        0x8013e66,
        0x8013ee6,
        0x8013f5e,
        0x801402a,
        0x8014058,
        0x80140f0,
        0x80141d2,
        0x801425a,
        0x80142c2,
        0x8014476,
        0x80145c6,
        0x80145f2,
        0x801464c,
        0x801475a,
        0x8014802,
        0x8014832,
        0x80148d0,
        0x8014972,
        0x80149a4,
        0x8014a42,
        0x8014ad6,
        0x8014b04,
        0x8014bb8,
        0x8014c5a,
        0x8014c88,
        0x8014d28,
        0x8014dba,
        0x8014de8,
        0x8014e84,
        0x8014f1e,
        0x8014f98,
        0x8014fca,
        0x801509a,
        0x8015328,
        0x8015392,
        0x80153c2,
        0x8015416,
        0x8015568,
        0x801559c,
        0x80155d0,
        0x8015602,
        0x8015636,
        0x801566a,
        0x801569e,
        0x80156e0,
        0x8015712,
        0x801578c,
        0x80157c0,
        0x8015800,
        0x8015832,
        0x8015864,
        0x8015896,
        0x80158c8,
        0x80158fa,
        0x801592c,
        0x801595e,
        0x8015a4a,
        0x8015bf4,
        0x8015c28,
        0x8015c5c,
        0x8015c8e,
        0x8015cc2,
        0x8015cf4,
        0x8015d26,
        0x8015d66,
        0x8015d96,
        0x8015e06,
        0x8015e36,
        0x8015e70,
        0x8015e9e,
        0x8015ecc,
        0x8015efa,
        0x8015f26,
        0x8015f56,
        0x8015f82,
        0x8015fae,
        0x8016020,
        0x801608a,
        0x8016156,
        0x8016204,
        0x8016238,
        0x8016334,
        0x801641c,
        0x8016508,
        0x8016594,
        0x801665e,
        0x8016712,
        0x80167ac,
        0x8016848,
        0x8016876,
        0x80168a4,
        0x8016980,
        0x80169de,
        0x8016b0e,
        0x8016bc0,
        0x8016c34,
        0x8016cf2,
        0x8016d88,
        0x8016e22,
        0x8016ec4,
        0x8016ef2,
        0x8017010,
        0x80170a6,
        0x80170d8,
        0x801710a,
        0x801713c,
        0x80171d4,
        0x8017420,
        0x80174a6,
        0x80175a6,
        0x80178b4,
        0x8017944,
        0x8017a78,
        0x8017cbe,
        0x8017d4c,
        0x8017e44,
        0x801815e,
        0x80181f0,
        0x801833c,
        0x80183f8,
        0x801849c,
        0x8018572,
        0x8018616,
        0x80186fe,
        0x80187e8,
        0x8018bb8,
        0x8018ca2,
        0x8018d9c,
        0x80191ea,
        0x801927c,
        0x80192e2,
        0x801943a,
        0x801959c,
        0x8019640,
        0x80196e8,
        0x801971c,
        0x80197c6,
        0x8019820,
        0x80199c2,
        0x8019baa,
        0x8019bd8,
        0x8019cdc,
        0x8019e48,
        0x8019eac,
        0x8019f5c,
        0x8019f94,
        0x801a1c0,
        0x801a24e,
        0x801a280,
        0x801a386,
        0x801a3f8,
        0x801a594,
        0x801a664,
        0x801a7f0,
        0x801a822,
        0x801a8d2,
        0x801a91c,
        0x801a966,
        0x801a9b0,
        0x801a9fa,
        0x801aa2c,
        0x801ab56,
        0x801abec,
        0x801ac90,
        0x801ad2c,
        0x801add4,
        0x801af2a,
        0x801af5c,
        0x801afaa,
        0x801b000,
        0x801b04e,
        0x801b0a6,
        0x801b0f4,
        0x801b142,
        0x801b190,
        0x801b1de,
        0x801b236,
        0x801b260,
        0x801b2ac,
        0x801b2e0,
        0x801b318,
        0x801b350,
        0x801b3b6,
        0x801b3ec,
        0x801b42a,
        0x801b460,
        0x801b494,
        0x801b4c8,
        0x801b4fc,
        0x801b5ca,
        0x801b5fe,
        0x801b6c0,
        0x801b6ee,
        0x801b7a6,
        0x801b7d4,
        0x801b88a,
        0x801b8b8,
        0x801b9c6,
        0x801b9fa,
        0x801baa4,
        0x801bb58,
        0x801bbe2,
        0x801bcc0,
        0x801bd7c,
        0x801bdae,
        0x801bde0,
        0x801be66,
        0x801bf8c,
        0x801c30a,
        0x801c37e,
        0x801c5fc,
        0x801c692,
        0x801c6fc,
        0x801c766,
        0x801c908,
        0x801c938,
        0x801c9fc,
        0x801cfc6,
        0x801d084,
        0x801d0b8,
        0x801d1e4,
        0x801d216,
        0x801d51e,
        0x801d550,
        0x801d7aa,
        0x801d7da,
        0x801d808,
        0x801d834,
        0x801d860,
        0x801d88c,
        0x801d948,
        0x801d972,
        0x801da60,
        0x801da8e,
        0x801dae8,
        0x801db16,
        0x801dbce,
        0x801dc02,
        0x801dc36,
        0x801dc6a,
        0x801dd3e,
        0x801dd72,
        0x801de3c,
        0x801de70,
        0x801df02,
        0x801dfc6,
        0x801e154,
        0x801e38c,
        0x801e418,
        0x801e4e0,
        0x801e510,
        0x801e5a0,
        0x801e66a,
        0x801e740,
        0x801e83e,
        0x801e872,
        0x801e8a6,
        0x801e954,
        0x801e9f6,
        0x801eaf8,
        0x801eb28,
        0x801eb58,
        0x801eb88,
        0x801ec1e,
        0x801ecb6,
        0x801ed44,
        0x801ee14,
        0x801ee42,
        0x801ef14,
        0x801efc6,
        0x801f058,
        0x801f122,
        0x801f156,
        0x801f1f0,
        0x801f288,
        0x801f36c,
        0x801f3a0,
        0x801f3d4,
        0x801f408,
        0x801f4a0,
        0x801f530,
        0x801f5ae,
        0x801f62a,
        0x801f6ae,
        0x801f7da,
        0x801f918,
        0x801f9b6,
        0x801fa60,
        0x801fb26,
        0x801fb58,
        0x801fbe2,
        0x801fc5e,
        0x801fd30,
        0x801fd62,
        0x801fe40,
        0x801fe74,
        0x801ff0c,
        0x801ff3c,
        0x801ff6a,
        0x801ff98,
        0x8020080,
        0x802010e,
        0x8020182,
        0x80201f2,
        0x802027c,
        0x80203ee,
        0x8020420,
        0x8020454,
        0x80204d8,
        0x802059a,
        0x8020646,
        0x802070a,
        0x80207c4,
        0x80207f4,
        0x8020826,
        0x8020970,
        0x80209d0,
        0x80209fa,
        0x8020b02,
        0x8020b2c,
        0x8020b8c,
        0x8020bb6,
        0x8020cc2,
        0x8020e3e,
        0x8020f00,
        0x8020fa4,
        0x8021048,
        0x80210de,
        0x8021110,
        0x802119c,
        0x80212a8,
        0x802138c,
        0x80213b8,
        0x80213e6,
        0x80214e6,
        0x802173e,
        0x80217d6,
        0x80218c6,
        0x8021cc6,
        0x8021d98,
        0x8022180,
        0x80221fc,
        0x8022294,
        0x8022366,
        0x802240e,
        0x802262c,
        0x802271c,
        0x80227ee,
        0x8022872,
        0x8022960,
        0x80229ca,
        0x80229fa,
        0x8022a28,
        0x8022ab2,
        0x8022ae0,
        0x8022bd0,
        0x8022c5e,
        0x8022d4e,
        0x8022e86,
        0x8022f30,
        0x8022fa4,
        0x8022fd4,
        0x80231f4,
        0x80232c4,
        0x8023354,
        0x80233d4,
        0x8023404,
        0x80235ca,
        0x8023644,
        0x80236cc,
        0x80238f8,
        0x8029c96,
        0x802edba,
        0x802edee,
        0x802ee22,
        0x802ee56,
        0x802ee8a,
        0x802ef26,
        0x802f1d6,
        0x802f2bc,
        0x802f36a,
        0x802f398,
        0x802f42a,
        0x802f458,
        0x802f4ce,
        0x802f4fe,
        0x802f52e,
        0x802f616,
        0x802f644,
        0x802f6e2,
        0x802f7d6,
        0x802fa10,
        0x802fc84,
        0x802fea2,
        0x802feec,
        0x802ff7e,
        0x8030048,
        0x80300fa,
        0x8030160,
        0x80301bc,
        0x80301ec,
        0x803027a,
        0x8030358,
        0x803038c,
        0x80308c8,
        0x803098e,
        0x80309c2,
        0x80309f6,
        0x8030a88,
        0x8030ab6,
        0x8030b44,
        0x8030bca,
        0x8030bf8,
        0x8030ce2,
        0x8030ed4,
        0x8030f08,
        0x8030f3c,
        0x8030fea,
        0x8031012,
        0x80310bc,
        0x80327fa,
        0x8032e74,
        0x8032f02,
        0x8032f84,
        0x8032fb8,
        0x803303e,
        0x8033104,
        0x8033138,
        0x803343a,
        0x80334f0,
        0x803351a,
        0x80335b8,
        0x8033630,
        0x8033660,
        0x8033690,
        0x80337f4,
        0x803381e,
        0x8033916,
        0x803399e,
        0x80339c8,
        0x8033a92,
        0x8033abc,
        0x8033ae6,
        0x8033c14,
        0x8046b48,
        0x8046bac,
        0x8046c10,
        0x8046c48,
        0x8046cfe,
        0x8046d62,
        0x8046d96,
        0x8046e1c,
        0x8046ec6,
        0x8046f2a,
        0x8046f5e,
        0x8046ffa,
        0x80470ae,
        0x80470e2,
        0x8047196,
        0x80471ca,
        0x8047378,
        0x80473a6,
        0x8047442,
        0x804746c,
        0x8047550,
        0x8047634,
        0x80476f2,
        0x8047720,
        0x80477d4,
        0x8047806,
        0x80478d0,
        0x8047900,
        0x80479cc,
        0x80479fe,
        0x8047acc,
        0x8047b3a,
        0x8047bd0,
        0x8047c40,
        0x8047f9e,
        0x8048026,
        0x80484f0,
        0x804851a,
        0x8048642,
        0x80486a6,
        0x80486da,
        0x8048776,
        0x8048828,
        0x804885a,
        0x80488f8,
        0x8048a16,
        0x8048a4a,
        0x8048afc,
        0x8048b2e,
        0x8048bf2,
        0x8048c24,
        0x8048d18,
        0x8048dac,
        0x8048e0e,
        0x8050474,
        0x80504e2,
        0x8050546,
        0x805057a,
        0x80505fe,
        0x80506c0,
        0x80506f4,
        0x80509f0,
        0x8050aae,
        0x8050ae0,
        0x8050b80,
        0x8050bee,
        0x8050c1c,
        0x8050c4a,
        0x8050c78,
        0x8050daa,
        0x8050dd2,
        0x8050e98,
        0x8052494,
        0x80524c8,
        0x80524fc,
        0x805253c,
        0x8052570,
        0x80525e2,
        0x8052616,
        0x8052680,
        0x80526b4,
        0x8052720,
        0x8052752,
        0x805288a,
        0x8052908,
        0x805299e,
        0x8052a64,
        0x8052ade,
        0x8052b58,
        0x8052bbe,
        0x8054bc8,
        0x8054bfe,
        0x8054c32,
        0x8054fce,
        0x8055022,
        0x8055054,
        0x80550aa,
        0x80550e8,
        0x805511a,
        0x8055170,
        0x80551ae,
        0x80551e0,
        0x8055238,
        0x805526a,
        0x80552a8,
        0x80552e8,
        0x805531a,
        0x805564a,
        0x80556a6,
        0x80556ce,
        0x80557c6,
    ]
    #for adr in md380_create_menu_entry_hooks:
    #    merger.hookbl(adr, sapplet.getadr("md380_create_menu_entry_hook"))
    new_adr = sapplet.try_getadr("SysTick_Handler");

    if new_adr != None:
        vect_adr = 0x800C03C;  # address inside the VT for SysTick_Handler
        exp_adr  = 0x80D3673;  # expected 'old' content of the above VT entry
        old_adr  = merger.getword(vect_adr); # original content of the VT entry
        new_adr |= 0x0000001;  # Thumb flag for new content in the VT
        if( old_adr == exp_adr ) :
           print("Patching SysTick_Handler in VT addr 0x%08x," % vect_adr)
           print("  old value in vector table = 0x%08x," % old_adr)
           print("   expected in vector table = 0x%08x," % exp_adr)
           print("  new value in vector table = 0x%08x." % new_adr)
           merger.setword( vect_adr, new_adr, old_adr);
           print("  SysTick_Handler successfully patched.")
        else:
           print("Cannot patch SysTick_Handler() !")
    else:
           print("No SysTick_Handler() found in the symbol table. Building firmware without.")
		   
    #Change TIM12 IRQ Handler to new one
    merger.setword(0x0800c0ec, sapplet.getadr("New_TIM12_IRQHandler")+1);

    print("Merging %s into %s at %08x" % (
        sys.argv[2],
        sys.argv[1],
        index))

    i = 0
    for b in bapplet:
        merger.setbyte(index + i, bapplet[i])
        i += 1

    merger.export(sys.argv[1])
