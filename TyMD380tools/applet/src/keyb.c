/*
 *  keyb.c
 * 
 */

#include "config.h"


#include "md380.h"
#include "debug.h"
#include "netmon.h"
//#include "mbox.h"
#include "console.h"
#include "syslog.h"
#include "lastheard.h"
#include "radio_config.h"
//#include "sms.h"
//#include "beep.h"
#include "codeplug.h"
#include "radiostate.h"
#include "printf.h"
#include "menu.h" // create_menu_entry_set_tg_screen() called from keyb.c !

#include <stdint.h>
#include "spiflash.h"
#include "keyb.h"
#include "etsi.h"
#include "usersdb.h"
#include "menu.h"


extern int     ad_hoc_talkgroup;

uint8_t kb_backlight=0; // flag to disable backlight via sidekey.
// Other keyboard-related variables belong to the original firmware,
// e.g. kb_keypressed, address defined in symbols_d13.020 (etc).

int Menu_IsVisible() { return 0; }

// Values for kp
// 1 = pressed
// 2 = release within timeout
// 1+2 = pressed during rx
// 4+1 = pressed timeout
// 8 = rearm
// 0 = none pressed
inline int get_main_mode()
{
	if (!gui_opmode1 & 0x7F) {
		syslog_printf("gui: %d - ");
	}
    return gui_opmode1 & 0x7F ;
}

extern void enable_backlight(uint32_t, uint32_t);

void reset_backlight()
{
	// struct @ 0x2001dadc
	backlight_timer = 5 * 500;

	// enabling backlight again.
	//MOVS    R1, #0x10
	//LDR.W   R0, =GPIOE_MODER
	enable_backlight(0x40021000, 0x10);
}


void copy_dst_to_contact()
{

	int dst = rst_dst;
	//int dst = 3148;
	extern wchar_t channel_name[];
	extern int ad_hoc_talkgroup;
	extern int ad_hoc_call_type;

	ad_hoc_talkgroup = dst;
	ad_hoc_call_type = CONTACT_GROUP;
	checkAdHocTG();
	
	/*{
		contact_t selContact;
		selContact.id_l = ad_hoc_talkgroup & 0xFF;
		selContact.id_m = (ad_hoc_talkgroup >> 8) & 0xFF;
		selContact.id_h = (ad_hoc_talkgroup >> 16) & 0xFF;
		selContact.type = CONTACT_GROUP;

		md380_spiflash_write(&selContact, 0x13FFDC, 3);
	}*/
	
	syslog_printf("Set AdhocTG: %d\r\n", ad_hoc_talkgroup);

	
	//wchar_t *p = (void*)0x2001e1f4 ;
	wchar_t *p = (void*)channel_name;

	/*if (rst_grp) {
		//contact.type = CONTACT_GROUP;
		contact2.type = CONTACT_GROUP;
		snprintfw(p, 16, "TG %d", dst);
	}
	else {
		snprintfw(p, 16, "U %d", dst);
		//contact.type = CONTACT_USER;
		contact2.type = CONTACT_USER;
	}*/
}

int beep_event_probe = 0 ;

void switch_to_screen( int scr )
{
	nm_screen = scr;
	// cause transient -> switch back to idle screen.
    gui_opmode2 = OPM2_MENU ;
    gui_opmode1 = SCR_MODE_IDLE | 0x80 ;

	
}

extern int hexScrollWindowIndex;

//#if defined(FW_D13_020) || defined(FW_S13_020)
#if defined(FW_S13_020)
extern void gui_control( int r0 );
#else
#define gui_control(x)
#endif

extern void draw_zone_channel(); // TODO.

static long dumpOffset = 0x204003;

static long getfirstnumber2(const char * p) {
	char buffer[64];
	//long pRnd = (long)p & 0xFFFFFFF0;
	//if (pRnd != p) {
	//  getdata(buffer, pRnd, 16);
	// memcpy(buffer, buffer + ((long)p - pRnd), ((long)p - pRnd));
	//}
	//else {
	md380_spiflash_read(buffer, (long)p, 16);
	//}
	//long retid = get_adr((*(adr_t*)buffer));
	long retid = ((*(long*)buffer)) & 0xFFFFFF;
	//syslog_printf("\n%08X: %08X %08X", (long)p, *(long*)(buffer), retid);
	return retid;
}

extern void rx_screen_blue_hook(unsigned int bg_color);

static int Flashsize = 0x1000;
uint32_t Flashadr = 0x203C00;

uint32_t ptrrr = 0x20000000 + 0x10000;

extern void md380_Flash_Log();


static uint32_t *ptrToData = 0x2001C2F4;


int handle_hotkey( int keycode )
{
	char lat[23] = { 0 };
	char lng[23] = { 0 };
    reset_backlight();
	long idd;

	int i = 0;
	

	if (nm_screen) {
		switch (keycode) {
		case 0:
			break;
			clog_redraw();
			switch_to_screen(6);
			break;

		case 1:
			//draw_zone_channel();

			//long pRnd = (long)p & 0xFFFFFFF0;
			//if (pRnd != p) {
			//  getdata(buffer, pRnd, 16);
			// memcpy(buffer, buffer + ((long)p - pRnd), ((long)p - pRnd));
			//}
			//else {


			//WORKS!!
			////syslog_printf("\nDumpin...%X", ptrrr);
			////for (i = 0; i < 0x20; i += 1) {
			////	md380_spiflash_write((void*)(ptrrr +(i* 1024)), Flashadr + (i * 1024), 1024);
			////	//syslog_printf("\n %x ...", i* 1024);
			////}
			////ptrrr += 0x20 * 1024;
			////Flashadr += 0x20 * 1024;
			////syslog_printf("\n %x ...", Flashadr);
			
			
			//clog_redraw();
			//syslog_printf("\nmain_mode: %d", idd);
			////menu_t *menu_mem;
			////md380_Flash_Log();

			//{
			//

			//	syslog_printf("FLASHWRITE %x %d\n", Flashadr, Flashsize);
			//	// enable write

			//	for (i = 0; i<Flashsize; i = i + 256) {
			//		int page_adr;
			//		page_adr = Flashadr + i;
			//		//syslog_printf("%d %x\n", i, page_adr);
			//		//md380_spiflash_wait();

			//		md380_spiflash_enable();
			//		md380_spi_sendrecv(0x6);
			//		md380_spiflash_disable();

			//		md380_spiflash_enable();
			//		md380_spi_sendrecv(0x2);
			//		//syslog_printf("%x ", ((page_adr >> 16) & 0xff));
			//		md380_spi_sendrecv((page_adr >> 16) & 0xff);
			//		//syslog_printf("%x ", ((page_adr >> 8) & 0xff));
			//		md380_spi_sendrecv((page_adr >> 8) & 0xff);
			//		//syslog_printf("%x ", (page_adr & 0xff));
			//		md380_spi_sendrecv(page_adr & 0xff);
			//		for (int ii = 0; ii < 256; ii++) {
			//			md380_spi_sendrecv(((char*)ptrrr)[ii + (i* 256)]);
			//		}
			//		md380_spiflash_disable();
			//		md380_spiflash_wait();
			//		
			//	}
			//	syslog_printf("Done\n");
			//}
			//Flashadr += Flashsize;
			//ptrrr += Flashsize;
			//idd = getfirstnumber2((char*)dumpOffset);
			
			//idd = get_main_mode();

			
			//syslog_printf("\nmain_mode: %d", idd);
			//syslog_printf("\ngui_opmode2: %d", gui_opmode2);
			//syslog_printf("\ngui_opmode3: %d", gui_opmode3);
			break;

		case 20:
		case 2:
			//ptrToData += 0x10;
			//syslog_redraw();
			switch_to_screen(1);
			break;
			
			
		//{
		//	syslog_printf("FLASHERASE %08X \n", Flashadr);
		//	//      spiflash_wait();     
		//	//      spiflash_block_erase64k(adr);


		//	md380_spiflash_enable();
		//	md380_spi_sendrecv(0x6);
		//	md380_spiflash_disable();

		//	md380_spiflash_enable();
		//	md380_spi_sendrecv(0xd8);
		//	md380_spi_sendrecv((Flashadr >> 16) & 0xff);
		//	md380_spi_sendrecv((Flashadr >> 8) & 0xff);
		//	md380_spi_sendrecv(Flashadr & 0xff);
		//	md380_spiflash_disable();
		//	syslog_printf("\n");
		//}
			
			//hexScrollWindowIndex += 4;
			break;
		case 3:
			if(!ad_hoc_talkgroup)
				copy_dst_to_contact();
			else {
				ad_hoc_talkgroup = 0;
				syslog_printf("Cleared AdHocTG\r\n");
			}
			//switch_to_screen(9);
			break;
		case 4:
			lastheard_redraw();
			switch_to_screen(4);
			break;
		case 5:
			syslog_clear();
			lastheard_clear();
			slog_clear();
			clog_clear();
			slog_redraw();
			nm_started = 0;	// reset nm_start flag used for some display handling
			nm_started5 = 0;	// reset nm_start flag used for some display handling
			nm_started6 = 0;	// reset nm_start flag used for some display handling
			break;
		case 6:
		{
			static int cnt = 0;
			syslog_clear();
			lastheard_clear();
			slog_clear();
			clog_clear();
			nm_started = 0;	// reset nm_start flag used for some display handling
			nm_started5 = 0;	// reset nm_start flag used for some display handling
			nm_started6 = 0;	// reset nm_start flag used for some display handling

			
			syslog_printf("  ~ Hex - %08X ~ \n", *(uint32_t*)(ptrToData));
			for (int i = 0; i < 6; i++) {
				for (int x = 0; x < 6; x++) {
					syslog_printf("%02X", *(uint8_t*)(ptrToData + x));
				}
				
				syslog_printf(" ");
				for (int x = 0; x < 6; x++) {
					syslog_printf("%c", *(char*)(ptrToData++));
				}
				syslog_printf("\n");
			}
			syslog_redraw();
			if (!Menu_IsVisible() && nm_screen) {
				switch_to_screen(3);  //change this back to 3

			}
			//*(uint32_t*)0x2001C898 = 4000;
			//*(uint32_t*)0x2001C8A0 = 4000;
			//syslog_printf("=POKED 4000! %d=\n", cnt++);
		}
		break;
		
		//case 10:
		case 13: //end call
				 //bp_send_beep(BEEP_TEST_1);
			if (nm_screen) {
				//channel_num = 0;
				switch_to_screen(0);
				//if(Menu_IsVisible()){
				//	channel_num = 0;
				//}
			}
			else if (!Menu_IsVisible()) {
				switch_to_screen(9);
				switch_to_screen(0);
			}
			break;
			
			

		//case 10:
		case 7:
			//Let 7 disable ad-hoc tg mode;
			if (!nm_screen && !Menu_IsVisible()) {
				ad_hoc_talkgroup = 0;
				
			}
			if (nm_screen) {
				//bp_send_beep(BEEP_TEST_1);
				switch_to_screen(0);
				//channel_num = 0;
			}
			/*else if (!Menu_IsVisible()) {
				switch_to_screen(9);
				switch_to_screen(0);
			}*/

			break;
		//case 21:
		case 8:
			//ptrToData -= 0x10;
			//bp_send_beep(BEEP_TEST_2);
			switch_to_screen(1);
			break;
		case 9:
			//bp_send_beep(BEEP_TEST_3);
			
			switch_to_screen(2);
			break;
		case 11:
			//gui_control(1);
			//bp_send_beep(BEEP_9);
			//beep_event_probe++ ;
			//sms_test2(beep_event_probe);
			//mb_send_beep(beep_event_probe);
			//ptrToData -= 0x10;
			//syslog_redraw();
			break;
		case 12:
			//gui_control(241);
			//bp_send_beep(BEEP_25);
			//beep_event_probe-- ;
			//sms_test2(beep_event_probe);
			//mb_send_beep(beep_event_probe);
			ptrToData += 0x10;
			syslog_redraw();
			break;
		
			// key '*'
		case 14:
			if (nm_screen != 9) {
				switch_to_screen(9);
				rx_screen_blue_hook(0xff8032);
			}
			else if (nm_screen == 9) {

				switch_to_screen(0);
			}
			break;

			// key '#'
		case 15:

			if (!Menu_IsVisible() && nm_screen) {
				syslog_redraw();
				switch_to_screen(3);  //change this back to 3
				
			}
			break;
		}
	}
	else {
		if (keycode == 15 ) {
			if (!Menu_IsVisible()) {
				syslog_redraw();
				switch_to_screen(3);
			}
		}
		else if (keycode == 14 && !nm_screen) {
			switch_to_screen(9);
			//channel_num=0;
			rx_screen_blue_hook(0xff8032);
		}
		/*else if (keycode == 10 && !nm_screen) {
			nm_screen = 10;
			gui_opmode1 = SCR_MODE_IDLE | 0x80;
			//switch_to_screen(9);
			//switch_to_screen(0);

			kb_keycode = keycode;
			kb_keypressed = 2;
			//kb_handler();
			return 0;
		}*/
		
	}
	return 1;
}



void trace_keyb(int sw)
{
    static uint8_t old_kp = -1 ;
    uint8_t kp = kb_keypressed ;
    
    if( old_kp != kp ) {
		syslog_printf("kp: %d %02x -> %02x (%04x) (%d)\n", sw, old_kp, kp, kb_row_col_pressed, kb_keycode );
        old_kp = kp ;
    }
}

int is_intercept_allowed()
{
	if (!is_netmon_enabled()){//|| Menu_IsVisible()) {
        return 0 ;
    }

	switch (gui_opmode2) {
		case OPM2_MENU:
			return 0;
		case 1:
			return 1;
			//case 2 : // voice
			//case 4 : // terminate voice
			//    return 1 ;
		default:
			return 1;
	}
    
    /**witch( get_main
		_mode() ) {
        case 27 :

		case 28 :
            return 1 ;
        default:
            return 0 ;
    }*/
    
    
}

int is_intercepted_keycode( int kc )
{
    switch( kc ) {
		//case 0 :
        case 1 :
		case 2 :
        case 3 :
        case 4 :
        case 5 :
        case 6 :
        case 7 :
        case 8 :
        case 9 :
		case 10:
        case 11 :
        case 12 :
		case 13 : //end call
		case 14 : // *
        case 15 : // #
            return 1 ;
        default:
            return 0 ;
    }    
}

int is_intercepted_keycode2(int kc)
{
	switch (kc) {
	
	case 10:
	case 20:
	case 21:
	//case 13: //end call
	//	return 1;
	default:
		return 0;
	}
}

extern void kb_handler();

static int nextKey = -1;

void kb_handle(int key) {
	int kp = kb_keypressed;
	int kc = key;

	/*if (key == 11 || key == 12) {
		kb_keycode = key;
		kb_keypressed = 2;
	}*/

	if (is_intercept_allowed()) {
		if (is_intercepted_keycode2(kc)) {
			if ((kp & 2) == 2) {
				handle_hotkey(kc);
				if (nm_screen) {
					kb_keypressed = 8;
				}
				return;
			}
		}
	}


}

void kb_handler_hook()
{

	//trace_keyb(0);

	kb_handler();

	//trace_keyb(1);

	//Menu_OnKey(KeyRowColToASCII(kb_row_col_pressed));
	//kb code down side 23


	if (nextKey > 0) {
		kb_keypressed = 2;
		kb_keycode = nextKey;
		nextKey = -1;
	}

	int kp = kb_keypressed;
	int kc = kb_keycode;

	/*if (kc == 20 || kc == 21) {
		kb_keypressed = 8;
		return;
	}*/

	// allow calling of menu during qso.
	// not working correctly.
	//if (kc == 3) {
	//	copy_dst_to_contact();
	//}
	//copy_dst_to_contact();
	if (is_intercept_allowed())
	{
		if (is_intercepted_keycode(kc)) {
			if ((kp & 2) == 2) {
				kb_keypressed = 8;
				handle_hotkey(kc);
				return;
			}
		}
	}
	/*else if (kc == 1) {
		kb_keypressed = 8;
		syslog_printf("\nDumpin...%X", ptrrr);
		for (int i = 0; i < 0x20; i += 1) {
			md380_spiflash_write((void*)(ptrrr + (i * 1024)), Flashadr + (i * 1024), 1024);
			//syslog_printf("\n %x ...", i* 1024);
		}
		ptrrr += 0x20 * 1024;
		Flashadr += 0x20 * 1024;
		syslog_printf("\n %x ...", Flashadr);
	}*/

   /* if ( kc == 17 || kc == 18 ) {
      if ( (kp & 2) == 2 || kp == 5 ) { // The reason for the bitwise AND is that kp can be 2 or 3
        //handle_sidekey(kc, kp);         // A 2 means it was pressed while radio is idle, 3 means the radio was receiving
        return;
      }
    }*/



}
