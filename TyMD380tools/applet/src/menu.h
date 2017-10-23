/*
 *  menu.h
 * 
 */

#ifndef MENU_H
#define MENU_H

#ifdef __cplusplus
extern "C" {
#endif

#include <inttypes.h>
#include <stdint.h>

extern wchar_t  	md380_menu_edit_buf[];
//#if defined(FW_D13_020) || defined(FW_S13_020)
extern uint8_t      currently_selected_menu_entry;


//#endif
/* mn_editbuffer_poi / md380_menu_0x20001114 */
extern wchar_t *mn_editbuffer_poi;


/* Don't call functions without a complete prototype, e.g. from keyb.c . */
/* See also (more menu functions) : md380.h !                            */

void create_menu_entry_set_tg_screen(void);

extern void cfg_save();

typedef struct {
	const wchar_t* label;  // [0]
	void* green;           // [4]
	void* red;             // [8]
	uint8_t off12;         // [12]  
	uint8_t off13;         // [13]
	uint16_t item_count;   // [14]
	uint8_t off16;         // [16]
	uint8_t off17;         // [17]
	uint16_t unknown2;     // [18]
	uint32_t unk3;
	// sizeof() == 20 (0x14)
} menu_entry_t;




typedef struct {
	const wchar_t  *menu_title; // [0]
	menu_entry_t *entries; // [4]
	uint8_t numberof_menu_entries; // [8]
	uint8_t unknown_00;
	uint8_t unknown_01;
	uint8_t filler;
	uint32_t unk3;
} menu_t; // sizeof() == 16


extern menu_t md380_menu_memory[];

extern menu_entry_t md380_menu_mem_base[];


#ifdef __cplusplus
static_assert (sizeof(menu_entry_t) == 0x18, "menu_entry_t wrong size");
static_assert (sizeof(menu_t) == 16, "menu_t wrong size");
}
#endif

#endif /* MENU_H */

