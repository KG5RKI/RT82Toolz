/*! \file addl_config.c
  \brief .
*/

#include <string.h>

#include "printf.h"
#include "dmesg.h"
#include "md380.h"
#include "version.h"
#include "config.h"
#include "printf.h"
#include "spiflash.h"
#include "addl_config.h"
#include "radio_config.h"
#include "syslog.h"
#include "usersdb.h"

addl_config_t global_addl_config;

void cfg_read_struct(addl_config_t *cfg)
{
	char buf[1024*4];
	md380_spiflash_read(buf, spi_flash_addl_config_start, 1024*4);
	memcpy(cfg, buf, sizeof(addl_config_t));
}

void cfg_write_struct(addl_config_t *cfg)
{
	md380_spiflash_write(cfg, spi_flash_addl_config_start, spi_flash_addl_config_size);
}

uint8_t calc_crc(void *buf, int size)
{
	uint8_t crc = 0;
	uint8_t *p = buf;
	for (int i = 0; i<size; i++) {
		crc ^= p[i];
	}
	return crc;
}

#define R( ii, max ) { if( ii < 0 || ii > max ) { ii = 0 ; } }

int cfg_load()
{
	memset(&global_addl_config, 0, sizeof(addl_config_t));

	addl_config_t tmp;
	cfg_read_struct(&tmp);

	// the config in flash is bigger than mine.
	if (tmp.length > sizeof(addl_config_t)) {
		// we cannot crc what we have not read. (for now).
		LOGB("cfg oversized\n");
		return 0;
	}

	if (calc_crc(&tmp, sizeof(addl_config_t)) != 0) {
		// corrupted.
		LOGB("cfg crc fail\n");
		return 0;
	}

	// copy the smaller config into our bigger config.
	// leaving the rest 0.
	memcpy(&global_addl_config, &tmp, tmp.length);

	// range limit
	R(global_addl_config.userscsv, 3);			// 2017-02-19	0-disable 1-userscsv 2-talkeralias 3-both
	R(global_addl_config.micbargraph, 4);
	R(global_addl_config.debug, 1);
	R(global_addl_config.rbeep, 1);
	R(global_addl_config.promtg, 1);
	R(global_addl_config.boot_demo, 1);
	//    R(global_addl_config.boot_splash,0); // unused
	R(global_addl_config.netmon, 3);
	R(global_addl_config.datef, 8);
	R(global_addl_config.mic_gain, 2);
	R(global_addl_config.alt_text, 1);

	// restore dmrid
	//if ((global_addl_config.cp_override & CPO_DMR) == CPO_DMR) {
	//	md380_radio_config.dmrid = global_addl_config.dmrid;
	//}

	//    // restore radio name
	//    if (global_addl_config.userscsv == 1) {
	//        cfg_fix_radioname();
	//    }

	// global_addl_config.experimental is intentionally not permanent
	global_addl_config.experimental = 0;

#if defined(FW_D13_020) || defined(FW_S13_020)
#else
	global_addl_config.netmon = 0;
#endif

	if (tmp.length != sizeof(addl_config_t)) {
		global_addl_config.mic_gain = 0;
		global_addl_config.audio_leveling = 0;
		global_addl_config.display_options |= ShowLabelTG;
		return 0;
	}

	cfg_save();

	return 1;
}

void cfg_save()
{
	global_addl_config.crc = 0;
	global_addl_config.length = sizeof(addl_config_t);

	// The upper 4 bits must never be ZERO, to avoid 'complete darkness' of the display when ACTIVE .
	// Because in some radios, the PWM caused audible hum, use max brightness per default:
	// 2017-04-17 : Put this important note back in. Please don't remove this !
	if (!(global_addl_config.backlight_intensities & 0xF0))
	{
		global_addl_config.backlight_intensities |= 0xF0;
	}

	global_addl_config.crc = calc_crc(&global_addl_config, sizeof(addl_config_t));

	cfg_write_struct(&global_addl_config);
}

int cfg_tst_display_flag(addl_config_t* cfg, char flg) {
	return cfg->display_options & (flg != 0);
}

void cfg_set_radio_name()
{
	//    char callsign[10] = {0x00};
	//
	//    if (get_dmr_user_field(2, callsign, global_addl_config.dmrid, 10) == 0) {
	//        strncpy(callsign, "UNKNOWNID", 10);
	//    }
	//    
	//    // TODO: fix type in addl_config, or convert during boot.
	////    wide_sprintf((wchar_t *)&global_addl_config.rname[0], "%s", callsign);
	//    snprintfw(global_addl_config.rname, 10, "%s", callsign);
	//    global_addl_config.rname[9] = 0x00;
	//
	//    cfg_save();
	//    cfg_fix_radioname();
}

void init_global_addl_config_hook(void)
{
	LOGB("booting\n");

	//Initialize config values if first time
	if (!cfg_load()) {
		global_addl_config.fg_color = 0x4F21;
		global_addl_config.bg_color = 0x10C0;
		global_addl_config.sel_fg_color = 0xB658;
		global_addl_config.sel_bg_color = 0xCB40;
		global_addl_config.edit_fg_color = 0x9;
		global_addl_config.edit_bg_color = 0x9;
		global_addl_config.mic_gain = 0;
		global_addl_config.alt_text = 0;
		global_addl_config.display_options |= ShowLabelTG;
	}

	//#ifdef CONFIG_MENU
	md380_create_main_menu_entry();
	// Ex: warning: implicit declaration of function 'md380_create_main_menu_entry'  .
	//  Indeed. Cured 2017-04-17 by fixing a typo in md380.h" .
	//  ( md380_create_main_meny_entry(void) -> md380_create_main_menu_entry ) .
	//#endif    
}
