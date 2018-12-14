#include <idc.idc>

// kg5rki
// 12/13/2018




static RemoveAllChunks(address)
{
	auto a, b;
	a = NextFuncFchunk(address, address);
	b=0;
	while(a != BADADDR)
	{
		RemoveFchunk(address, a);
		a = NextFuncFchunk(address, address);
		b = b +1;
	}
	Message(form("function at 0x%08X, removed %d chunks\n",address,b));
}


/*
static makeKey(bytes, name, startAddr)
{
	auto cqw, stype, offset, ret;
	offset = FindBinary(startAddr, SEARCH_DOWN, bytes);
	if(offset != BADADDR)
	{
		cqw = Dword(offset);
		if(cqw == 0x10)
			stype = form("XECRYPT_RSAPUB_1024");
		else if(cqw == 0x18)
			stype = form("XECRYPT_RSAPUB_1536");
		else if(cqw == 0x20)
			stype = form("XECRYPT_RSAPUB_2048");
		else if(cqw == 0x40)
			stype = form("XECRYPT_RSAPUB_4096");
		else
		{
			Message(form("Could not make %s struct offset: 0x%08x, unknown CQW 0x%x\n", name, offset, cqw));
			return;
		}
		ret = MakeStructEx(offset, -1, stype);
		if(ret == 0)
			Message(form("Could not make %s struct type %s offset: 0x%08x err: %x\n", name, stype, offset, ret));
		else
			Message(form("Key struct %s marked at offset: 0x%08x\n", name, offset));
		MakeName(offset, name);
	}
	else
		Message(form("Did not find %s\n", name));
	return offset;
}*/

static nameBinaryFunction(startAddr, bytes, name)
{
	auto offset;
	offset = FindBinary(startAddr, SEARCH_DOWN, bytes);
	if(offset != BADADDR)
	{
		MakeName(offset, name);
		MakeFunction(offset, BADADDR);
		Message(form("Named function %s at offset: 0x%08x\n", name, offset));	
	}
	else
		Message(form("Did not find binary function %s\n", name));	

	return offset;
}

static nameBinary(startAddr, bytes, len, name)
{
	auto offset;
	offset = FindBinary(startAddr, SEARCH_DOWN, bytes);
	if(offset != BADADDR)
	{
		MakeByte(offset);
		MakeArray(offset, len);
		MakeName(offset, name);
		Message(form("Named binary array %s at offset: 0x%08x\n", name, offset));
		offset = offset + len;
	}
	else
		Message(form("Did not find binary data %s\n", name));	
	return offset;
}

static nameBinaryString(startAddr, bytes, len, name)
{
	auto offset;
	offset = FindBinary(startAddr, SEARCH_DOWN, bytes);
	if(offset != BADADDR)
	{
		MakeStr(offset, offset+len);
		MakeName(offset, name);
		Message(form("Named binary string %s at offset: 0x%08x\n", name, offset));
		offset = offset + len;
	}
	else
		Message(form("Did not find binary string data %s\n", name));	
	return offset;
}

static nameFunctionFindBytes(name, bytes)
{
	auto ea, start;
	ea = FindBinary(0, SEARCH_DOWN, bytes);
	if(ea != BADADDR)
	{	
		start = GetFunctionAttr(ea,FUNCATTR_START);
		if(start != BADADDR)
		{
			MakeName(start, name);
			Message(form("Named function %s at offset: 0x%08x\n", name, start));
			ea = FindBinary(ea+4, SEARCH_DOWN, bytes);
			if(ea != BADADDR)
			{
				Message(form("# WARNING second instance found at 0x%x\n", name, ea));	
			}
		}
		else
				Message(form("could not find function start for %s in 0x%x\n", name, ea));	
	}
	else
		Message(form("Did not find binary function %s\n", name));	
}

static nameFunctionByXref(name, callname, xrnum)
{
	auto ea, ref, start, xrc;
	ea = LocByName(callname);
	if(ea != BADADDR)
	{
		ref = RfirstB(ea); // first xref
		if(ref != BADADDR)
		{
			xrc = 1;
			while(xrc < xrnum)
			{
				ref = RnextB(ea, ref);
				xrc = xrc + 1;
			}
			if(ref != BADADDR)
			{
				start = GetFunctionAttr(ref,FUNCATTR_START);
				if(start != BADADDR)
				{
					MakeName(start, name);
					Message(form("Named function %s at offset: 0x%08x\n", name, start));
				}
				else
					Message(form("cound not find function start for %s at %08x!!\n", name, ref));
			}
			else
				Message(form("cound not find xref #%d calling %s to name %s!!\n", xrnum, callname, name));
		}
	}
	else
		Message(form("cound not find caller %s to name %s!!\n", callname, name));
}


static nameByte(offset, name)
{
	MakeByte(offset);
	MakeName(offset, name);
}

static nameWord(offset, name)
{
	MakeWord(offset);
	MakeName(offset, name);
}

static nameDword(offset, name)
{
	MakeDword(offset);
	MakeName(offset, name);
}

/*static nameBasics()
{
	nameWord(0x0, "Magic");
	// MakeStructEx(0, -1, "BLDR");
	// MakeName(0, "HvHdr");

	nameDword(0x38, "pKeyVault");
	
	MakeByte(Dword(0x44));
	nameDword(Dword(0x44), "PteTable");
	MakeDword(Dword(0x48));
	
	nameDword(0x50, "prKernelHvExportTable");
	nameByte(0x74, "ConsoleType");
	nameByte(0x75, "UpdateSequence");
	nameWord(0x76, "UpdateSequenceAllow");
	nameDword(0x78, "prXboxKrnlBaseVersion");
	nameDword(0x7C, "prHvBaseVersion");
	nameDword(0x80, "pHvTable");
	
	nameDword(0x3C, "pKeyPropertiesTbl"); // aray dword 0x0 terminated
	nameDword(Dword(0x3c), "KeyPropertiesTbl");
	nameDword(0x40, "pKeyvaultLookupTbl"); // array short 0x0 terminated
	nameDword(Dword(0x40), "KeyvaultLookupTbl");

	nameDword(0x30, "KeysStatus");
	nameDword(0x34, "pPirsKey");
	nameDword(0x10000, "g_dwHvpStackLock");

	
	// cpu key is stowed currently at 0x20
	MakeByte(0x20);
	MakeArray(0x20, 0x10);
	MakeName(0x20, "CpuKey");
	// xex2 is stowed currently at 0x54
	MakeByte(0x54);
	MakeArray(0x54, 0x10);
	MakeName(0x54, "Xex2Key");
	// transfor magic at 0x18
	MakeByte(0x18);
	MakeArray(0x18, 8);
	MakeName(0x18, "TransformMagic");
	
	MakeArray(0x100F0, 0x10);
	MakeName(0x100F0, "HV_ecc");
	
	nameFunctionByXref("XeCryptAesDmMac", "XeCryptAesEncrypt", 4);
		nameBinaryFunction(0, "38 60 02 00 64 63 80 00 78 63 07 C6 64 63 C8 00 4E 80 00 20", "HvpGetFlashBaseAddress");
	
	nameBinary(0, "C6 63 63 A5 F8 7C 7C 84 EE 77 77 99 F6 7B 7B 8D", 0x1000, "g_XeCryptAesE"); 
	nameBinaryString(0, "58 42 4F 58 33 36 30 58 45 58", 10, "XEXSalt"); // XBOX360XEX
	makeKey("00 00 00 20 00 00 00 03 00 00 00 00 00 00 00 00 DD 5F 49 6F 99 4D 37 BB", "CONSTANT_MASTER_KEY", 0); // DD5F496F994D37BB
	nameFunctionFindBytes("XeCryptAesKeyTable", "39 65 01 00 39 85 05 00 39 C5 09 00 39 E5 0D 00 38 85 11 10");
	MakeQword(sysent + i + 40);
	
	MakeComm(sysent + i, form("syscall %i", syscallnum));
	MakeUnknown(address, 8, 0);
	MakeNameEx(address, getSyscallName(syscallnum), 0);
}*/

static setupGeneric()
{
	auto currAddr, str;


}

static getVectorName(number) {
    auto funcName;
    if(number>15)
        funcName = form("IRQ_%i", number-16);
   
    // haha x360_imports.numberc has good numbereas
    if(number == 0) funcName = "idk";
    else if(number == 1) funcName = "RESET";
    else if(number == 2) funcName = "NMI";
    else if(number == 3) funcName = "HARD_FAULT";
    else if(number == 4) funcName = "MEM_MGMT_FAULT";
    else if(number == 5) funcName = "BUS_FAULT";
    else if(number == 6) funcName = "USAGE_FAULT";
    else if(number == 7) funcName = "reserved1";
    else if(number == 8) funcName = "reserved2";
    else if(number == 9) funcName = "reserved3";
    else if(number == 10) funcName = "reserved4";
    else if(number == 11) funcName = "SV_CALL";
    else if(number == 12) funcName = "DEBUG";
    else if(number == 13) funcName = "reserved5";
    else if(number == 14) funcName = "PendSV_Handler";
    else if(number == 15) funcName = "SysTickHandler";
    else if(number == 19) funcName = "RTC_WKUP_IRQHandler";
    else if(number == 22) funcName = "EXTI0_IRQHandler";
    else if(number == 23) funcName = "EXTI1_IRQHandler";
    else if(number == 24) funcName = "EXTI2_IRQHandler";
    else if(number == 41) funcName = "TIM1_UP_TIM10_IRQHandler";
    else if(number == 44) funcName = "TIM2_IRQHandler";
    else if(number == 45) funcName = "TIM3_IRQHandler";
    else if(number == 46) funcName = "TIM4_IRQHandler";
    else if(number == 58) funcName = "OTG_FS_WKUP_IRQHandler";
    else if(number == 59) funcName = "TIM8_BRK_TIM12_IRQHandler";
    else if(number == 60) funcName = "TIM8_UP_TIM13_IRQHandler";
    else if(number == 66) funcName = "md380_spiflash_handler";
    else if(number == 70) funcName = "TIM6_DAC_IRQHandler";
    else if(number == 71) funcName = "TIM7_IRQHandler";
    else if(number == 72) funcName = "DMA2_Stream0_IRQHandler";
   
    return funcName;   
}

static CreateVector(address, name)
{
	auto a, b;
	auto func_addr;
	
	func_addr = Dword(address);
    MakeName(func_addr-1, "_V_"+name);
	MakeCode(func_addr-1);
	MakeFunction(func_addr-1, BADADDR);
	
	MakeName(address, name);
    MakeDword(address);
	op_plain_offset(address, 0, 0);
}


static SetupVectors()
{
    auto i = 1;
    auto func_addr;
	auto b,c;
    auto baseaddr = 0x800C000;
    
    nameDword(baseaddr, "stack_pointer");
	op_plain_offset(baseaddr, 0, 0);
    
    while( i <= 96){
        if(i<16)
			CreateVector(baseaddr+(i*4), getVectorName(i));
		else{
			
			
			func_addr = Dword(baseaddr+(i*4));
			b = Word(func_addr+1);
			c = Word(func_addr+1);
			MakeCode(func_addr-1);
			MakeFunction(func_addr-1, BADADDR);
			if(b == 0xF7FF && c != 0xF7FF ){
				
					MakeName(func_addr-1, "j_V_"+getVectorName(i));
				    
					b = Rfirst0(func_addr+1);
					MakeName(b, "V_"+getVectorName(i));
					MakeCode(b);
					MakeFunction(b, BADADDR);
			}else{
				
				MakeName(func_addr-1, "V_"+getVectorName(i));
				MakeName(baseaddr+(i*4), getVectorName(i));
				MakeDword(baseaddr+(i*4));
				op_plain_offset(baseaddr+(i*4), 0, 0);
			}
			
		}
        i=i+1;
    }
    
}

static main() {	
	// 4.55 sys_nosys offset 0x264D0
	// 5.05 sysent offset 0x107C610
	// 6.00b1 sysent offset 
	
	// calculate sys_nosys
	/*auto sys_nosys = SegStart(FirstSeg()) + 0x264D0;
	
	// make pattern
	auto b = form("00 00 00 00 00 00 00 00 %X %X %X %X %X %X %X %X 00 00 00 00 00 00 00 00", (sys_nosys >> 0) & 0xFF, (sys_nosys >> 8) & 0xFF, (sys_nosys >> 16) & 0xFF, (sys_nosys >> 24) & 0xFF, (sys_nosys >> 32) & 0xFF, (sys_nosys >> 40) & 0xFF, (sys_nosys >> 48) & 0xFF, (sys_nosys >> 56) & 0xFF);
	*/
	// search for sysent table
	
	SetupVectors();
	
}
















