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
	
    merger.hookbl(0x080299EA, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x080334D4, sapplet.getadr("rx_screen_blue_hook"), 0)
    merger.hookbl(0x0803BD1A, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    #merger.hookbl(0x08032588, sapplet.getadr("rx_screen_blue_hook"), 0)
    #merger.hookbl(0x080325C2, sapplet.getadr("rx_screen_blue_hook"), 0)
	
    #merger.hookbl(0x080D8A20, sapplet.getadr("usb_upld_hook"), 0x080D94BC)  # Old handler adr.
	
    # keyboard
    merger.hookbl(0x0806E6D2, sapplet.getadr("kb_handler_hook"));
	
    #merger.hookbl(0x0800E4B8, sapplet.getadr("print_date_hook"), 0)
    merger.hookbl(0x0802B230, sapplet.getadr("draw_statusline_hook"))
   
    merger.hookbl(0x08064B74, sapplet.getadr("init_global_addl_config_hook"), 0)

    aes_cipher_hook_list = [0x0802CD8A, 0x0802D6FC]
    for adr in aes_cipher_hook_list:
        merger.hookbl(adr, sapplet.getadr("aes_cipher_hook"))
   

    # Hook lots of AMBE2+ encoder code and hope our places are correct.
    ambelist = [
        0x806b4de,
        0x806b616,
        0x806b66e,
        0x806b7bc,
        0x806b832,
        0x806b9ac,
        0x806ba2c,
        0x806bb98,
        0x806bbce,
    ]
    #for adr in ambelist:
    #    merger.hookbl(adr, sapplet.getadr("ambe_encode_thing_hook"))
   
     # Hook calls within the AMBE2+ decoder.
    unpacklist = [
        0x8049e06,
        0x8049e12,
        0x8049e2a,
        0x8049e36,
        0x806c192,
        0x806c6be,
        0x806c712,
        0x806c768,
    ]
    #for adr in unpacklist:
    #    merger.hookbl(adr, sapplet.getadr("ambe_unpack_hook"))
   
    
    wavdeclist = [
	    0x806b26c,
        0x806bee0,
        0x806c036,
        0x806c348,
        0x806c384,
        0x806c444,
        0x806c480,
    ]
    #for adr in wavdeclist:
    #    merger.hookbl(adr, sapplet.getadr("ambe_decode_wav_hook"))
		
    draw_datetime_row_list = [
        0x802a498,
        0x802aa0c,
        0x802aa72,
        0x802ab70,
        0x802abd4,
        0x802ac26,
        0x802ac92,
        0x803e144,
        0x803e988
    ]
    for adr in draw_datetime_row_list:
        merger.hookbl(adr, sapplet.getadr("draw_datetime_row_hook"))
	
    dmr_call_start_hook_list = [0x804c984, 0x804c9ea, 0x804ca12, 0x804cfe2]
    for adr in dmr_call_start_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_call_start_hook"))
		
    merger.hookbl(0x0804CFEA, sapplet.getadr("dmr_call_end_hook"))
	
    dmr_CSBK_handler_hook_list = [0x0804CC60, 0x0804CFF2]
    for adr in dmr_CSBK_handler_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_CSBK_handler_hook"))
		
    dmr_handle_data_hook_list = [0x0804D01E, 0x0804D028, 0x0804D086]
    for adr in dmr_handle_data_hook_list:
        merger.hookbl(adr, sapplet.getadr("dmr_handle_data_hook"))
		
	# os semaphore hook .. now we can crate own semaphores
    #merger.hookbl(0x08060AFE, sapplet.getadr("OSSemCreate_hook"), 0)
	
    # other OSMboxPend hooks
    mbx_pend_list = [
        0x804291e,
        0x80586b2,
        0x80592fe,
        0x805981e,
        0x805b616,
        0x80657b0,
        0x80657da
    ]
    for adr in mbx_pend_list:
        merger.hookbl(adr, sapplet.getadr("OSMboxPend_hook"))
	
	
    merger.hookbl(0x08011770, sapplet.getadr("f_1444_hook"))
	
    merger.hookbl(0x0800E610, sapplet.getadr("print_date_hook"), 0)
    
    # hooks regarding the beep_process
    #beep_process_list = [
    #    0x08043900, 0x0804400E, 0x08044056 ,  # roger beep 0x285
    #]
    #for adr in beep_process_list:
    #    merger.hookbl(adr, sapplet.getadr("F_294_replacement"), 0)
		
    #merger.hookstub2(0x800C93E, sapplet.getadr("create_menu_entry_rev"))
	
				  
    drwbmplist = [
        0x800d18c,
        0x800ee24,
        0x800ee32,
        0x800ee4e,
        0x800ee5c,
        0x800eeda,
        0x800eee8,
        0x800ef04,
        0x800ef12,
        0x800ef6e,
        0x800ef9a,
        0x800efc6,
        0x800eff2,
        0x800f01e,
        0x800f04a,
        0x800f104,
        0x800f112,
        0x800f162,
        0x800f1dc,
        0x800f1ea,
        0x800f23a,
        0x8029a0c,
        0x802ad80,
        0x802ad8e,
        0x802b256,
        0x802b262,
        0x80337ee,
        0x803381c,
        0x8033828,
        0x803384c,
        0x803388a,
        0x80338a2,
        0x80362c2,
        0x80362f8,
        0x8036322,
        0x803634c,
        0x803636a,
        0x8036442,
        0x803648e,
        0x80364b4,
        0x8036510,
        0x8036524,
        0x8036594,
        0x80365a8,
        0x80365e2,
        0x8036626,
        0x8036688,
        0x80366cc,
        0x803679a,
        0x803a6ce,
        0x803a778,
        0x803a860,
        0x803a9c6,
        0x803aa5a,
        0x803ab72,
        0x803ac56,
        0x803ace0,
        0x803ae34,
        0x803ae40,
        0x803af62,
        0x803afee,
        0x803b0de,
        0x803b144,
        0x803b1c2,
        0x803bd3c,
        0x80481e8,
        0x8048210,
        0x8048264,
        0x80482a0,
        0x8053ea8
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
        0x800ee9a,
        0x800eea8,
        0x800f060,
        0x800f178,
        0x800f250,
        0x800f2ba,
        0x800f2c8,
        0x800f3ce,
        0x800f4b8,
        0x800f5d2,
        0x800f93a,
        0x800f954,
        0x800f992,
        0x800f99e,
        0x800f9aa,
        0x800f9bc,
        0x800f9d0,
        0x800f9dc,
        0x800faa6,
        0x800faca,
        0x800fae4,
        0x800fb06,
        0x800fb20,
        0x80277f2,
        0x8027800,
        0x8027810,
        0x8027a02,
        0x8027a12,
        0x8029524,
        0x8029cb6,
        0x8029f1e,
        0x802a6a0,
        0x802a8ca,
        0x802a9f0,
        0x802aa1e,
        0x802ab54,
        0x802ab82,
        0x802abe6,
        0x802ac38,
        0x80325c8,
        0x80325d4,
        0x80325e0,
        0x80325f2,
        0x80325fe,
        0x8032fdc,
        0x8032fe8,
        0x803307a,
        0x8033104,
        0x80331a6,
        0x8033280,
        0x803334a,
        0x803342a,
        0x8033436,
        0x80334ea,
        0x80334f6,
        0x8033698,
        0x803373c,
        0x8033756,
        0x80337b2,
        0x80337be,
        0x80337ca,
        0x803386e,
        0x80338be,
        0x80338ca,
        0x80339b8,
        0x8039bb0,
        0x8039bc4,
        0x803aaec,
        0x803ac40,
        0x803af78,
        0x803b04a,
        0x803b138,
        0x803b4b4,
        0x803b52c,
        0x803b8ce,
        0x803c82c,
        0x803c83e,
        0x803c84a,
        0x803c85e,
        0x803c86a,
        0x803df92,
        0x803df9e,
        0x803dfaa,
        0x803dff8,
        0x803e004,
        0x803e010,
        0x803e01c,
        0x803e028,
        0x803e034,
        0x803e040,
        0x803e134,
        0x803e140,
        0x803e158,
        0x803e16c,
        0x803e178,
        0x803e184,
        0x803e28a,
        0x803e296,
        0x803e2a2,
        0x803e2b6,
        0x803e2c2,
        0x803e2ce,
        0x803e2da,
        0x803e2e6,
        0x803e2f2,
        0x803e330,
        0x803e33c,
        0x803e3be,
        0x803e3ca,
        0x803e3fc,
        0x803e41c,
        0x803e428,
        0x803e458,
        0x803e464,
        0x803e49c,
        0x803e4cc,
        0x803e4d8,
        0x803e510,
        0x803e552,
        0x803e596,
        0x803e5d6,
        0x803e61a,
        0x803e626,
        0x803e658,
        0x803e678,
        0x803e684,
        0x803e6b4,
        0x803e6c0,
        0x803e6f6,
        0x803e726,
        0x803e732,
        0x803e768,
        0x803e7a8,
        0x803e7ea,
        0x803e822,
        0x803e856,
        0x803e878,
        0x803e884,
        0x803e890,
        0x803e89e,
        0x803e8aa,
        0x803e8b8,
        0x803e8da,
        0x803e8e8,
        0x803e8f4,
        0x803e900,
        0x803e918,
        0x803e978,
        0x803e984,
        0x803f4c4,
        0x803f4d0,
        0x803f5c8,
        0x803f5d6,
        0x80400f0,
        0x80400fc,
        0x8048230,
        0x804828e,
        0x8051f92,
        0x8051fb2,
        0x80653a2,
        0x80653b0,
        0x806d2fc
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
        0x800f3ba,
        0x800f3f4,
        0x800f464,
        0x800f4a4,
        0x800f530,
        0x800f570,
        0x800f5be,
        0x800f624,
        0x800f690,
        0x80333b2,
        0x803340e
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
        0x803279e,
        0x80327b6,
        0x80327ca,
        0x80327e2,
        0x803376e,
        0x8033778,
        0x8033792,
        0x803379e,
        0x803e088,
        0x803e0ac,
        0x803e0c8,
        0x803e0e2,
        0x803e104,
        0x803e120,
        0x803e3da,
        0x803e440,
        0x803e482,
        0x803e4be,
        0x803e4f6,
        0x803e538,
        0x803e574,
        0x803e636,
        0x803e69c,
        0x803e6de,
        0x803e718,
        0x803e750,
        0x803e790,
        0x803e7ca
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
        0x800fa92,
        0x8027c54,
        0x802841e,
        0x8028436,
        0x802846c,
        0x8028484,
        0x8033066,
        0x803326c,
        0x80332dc,
        0x803332e,
        0x80334a4,
        0x803dfd6,
        0x803e30e
    ]
    for adr in gfxdt10:
        merger.hookbl(adr, sapplet.getadr("gfx_drawtext2_hook"))
	
    rxscrn_hooks = [
        0x80299EA,
        0x080334D4,
        0x0803BD1A
    ]
    for adr in rxscrn_hooks:
        merger.hookbl(adr, sapplet.getadr("rx_screen_blue_hook"))
		
	# f_4315
    merger.hookbl(0x080298B8, sapplet.getadr("f_4315_hook"))
    merger.hookbl(0x080298EE, sapplet.getadr("f_4315_hook"))
	
    merger.hookbl(0x080652A8, sapplet.getadr("f_4225_hook"), 0)
    merger.hookbl(0x0803EC10, sapplet.getadr("f_4225_hook"), 0)

    #merger.hookbl(0x0801B9A4, sapplet.getadr("sub_801AC40"), 0)
	
    merger.hookbl(0x0801560C, sapplet.getadr("create_menu_utilies_hook"), 0)
	
	
    adhoc_tg_hooks = [
        #0x8050C5C,
		#0x08051C78,
		#0x0804E588, #also sets array of bits
		#0x0804FB4A,

        #0x08050C5C,
        #0x08051C78
        0x805d0e2,
        0x0804FE96,
        0x0804FF32,
	
  
        #0x804fd3a,
        #0x804fe96,
        #0x804ff32,
        #0x8050f6c,
        #0x8050f50, 
        #0x8050f38,
        #0x804fd92,
        #0x804fdd4,
        #0x804fe26,
        #0x8050ef2,
        #0x8050f0a,
        #0x8050f22,
        #0x805d0e2,
        #0x804fb4a,
        #0x8050eda,
		
		
        #0x8050e16,
        #0x8052080,
        #0x8052476,
        #0x80521b6,
        #0x805212e,
        #0x805ac02,
        #0x80517b2,
        #0x805183c,
        #0x80518a4,
        #0x8051bde,
        #0x8052454,
        #0x0804CC8E
	
    ]
    #for adr in adhoc_tg_hooks:
        #merger.hookbl(adr, sapplet.getadr("adhoc_tg_hook"))
	
 
    spiflashreadhooks = [
        0x801362c,
        0x8015374,
        0x8026aec,
        0x8026d4e,
        0x802d932,
        0x802d944,
        0x802d956,
        0x802d968,
        0x802dc10,
        0x802dc30,
        0x802dc56,
        0x802de30,
        0x802e85e,
        0x802e882,
        0x802f0ea,
        0x802f1f6,
        0x802fade,
        0x802fb5c,
        0x8034756,
        0x8034804,
        0x8034842,
        0x80431ba,
        0x8043292,
        0x80456d6,
        0x8045738,
        0x804578c,
		
		
    ]
    #for adr in spiflashreadhooks:
    #    merger.hookbl(adr, sapplet.getadr("spiflash_read_hook"))
	 # DL4YHF : We don't know here if the PWM'ed backlight, and thus
    #  SysTick_Handler() shall be included (depends on config.h) .
    # IF   the applet's symbol table contains a function named 'SysTick_Handler',
    # THEN patch its address, MADE ODD to indicate Thumb-code, into the
    # interrupt-vector-table as explained in applet/src/irq_handlers.c :
    # ex: new_adr = sapplet.getadr("SysTick_Handler"); # threw an exception when "not found" :(
    new_adr = sapplet.try_getadr("SysTick_Handler");

    if new_adr != None:
        vect_adr = 0x800C03C;  # address inside the VT for SysTick_Handler
        exp_adr  = 0x80D58B3;  # expected 'old' content of the above VT entry
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
