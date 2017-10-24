/*! \file main.c
  \brief MD380Tools Main Application
  
*/

#define COMPILING_MAIN_C 1  // flag to show warnings in headers only ONCE
                   // (e.g. "please consider finding symbols.." in gfx.h)

#include "stm32f4_discovery.h"
#include "stm32f4xx_conf.h" // again, added because ST didn't put it here ?

#include <string.h>
#include "dmesg.h"
#include "config.h"  // need to know CONFIG_DIMMED_LIGHT (defined in config.h since 2017-01-03)
#include "printf.h"
#include "version.h"
#include "usersdb.h"
#include "radiostate.h"
#include "codeplug.h"
#include "md380.h"
						  
GPIO_InitTypeDef  GPIO_InitStructure;

void Delay(__IO uint32_t nCount);

int     ad_hoc_talkgroup = 0; // "temporarily wanted" talkgroup, entered by user in the alternative menu
uint8_t ad_hoc_tg_channel= 0; // current channel number when the above TG had been set
int     ad_hoc_call_type = 0;
uint8_t channel_num;

/**
  * @brief  Delay Function.
  * @param  nCount:specifies the Delay time length.
  * @retval None
  */
void Delay(__IO uint32_t nCount)
{
  while(nCount--)
  {
  }
}

void sleep(__IO uint32_t ms){
  //Delay(0x3FFFFF);
  Delay(0x3fff*ms);
}



extern int read_contact(char *buffer, int Index);


//int md380_spiflash_write_hook(int a1, int a2, __int16 a3, int a4) {
//}

void read_contact_hook(char* buffer, int index) {
	if (ad_hoc_talkgroup || index == 50) {
		//*(uint16_t*)0x2001C1C0 = ad_hoc_talkgroup;
		//memcpy(buffer, &adhocUser2, sizeof(contact_t));
		memset(buffer, 0, sizeof(contact_t));
		contact_t* contacta = (contact_t*)buffer;
		contacta->id_l = ad_hoc_talkgroup & 0xFF;
		contacta->id_m = (ad_hoc_talkgroup >> 8) & 0xFF;
		contacta->id_h = (ad_hoc_talkgroup >> 16) & 0xFF;
		contacta->type = ad_hoc_call_type;
		return;
	}
	else {
		read_contact(buffer, index);
	}
}


static void do_jump(uint32_t stacktop, uint32_t entrypoint);

#define MFGR_APP_LOAD_ADDRESS     0x0800C000
#define SIDELOAD_RESET_VECTOR     8
#define SIDELOAD_APP_LOAD_ADDRESS 0x0809D000

static void abort_to_mfgr_app(void) {
	const uint32_t *app_base = (const uint32_t *)MFGR_APP_LOAD_ADDRESS;
	SCB->VTOR = MFGR_APP_LOAD_ADDRESS;
	do_jump(app_base[0], app_base[SIDELOAD_RESET_VECTOR]);
}

static void do_jump(uint32_t stacktop, uint32_t entrypoint)
{
	asm volatile(
		"msr msp, %0	\n"
		"bx	%1	\n"
		: : "r" (stacktop), "r" (entrypoint) : );
	// just to keep noreturn happy
	for (;;) ;
}



/* This copies a character string into a USB Descriptor string, which
   is a UTF16 little-endian string preceeded by a one-byte length and
   a byte of 0x03. */
const char *str2wide(char *widestring,
		     char *src){
  int i=0;
  
  while(src[i]){
    widestring[2*i]=src[i];//The character.
    widestring[2*i+1]=0;   //The null byte.
    i++;
  }
  widestring[2*i]=0;
  widestring[2*i+1]=0;
  
  return widestring;
}

extern void gfx_drawchar_pos(int r0, int r1, int r2);
extern void gfx_blockfill(int x_from, int y_from, int x_to, int y_to);
extern void gfx_drawtext7(const char *str, int x, int y); // firmware

												   // the intention is a string _without_ .. if it is too long.





/* Our RESET handler is called instead of the official one, so this
   main() method comes before the official one.  Our global variables
   have already been initialized, but the MD380 firmware has not yet
   been initialized because we haven't called it.
   
   So the general idea is to initialize our stuff here, then trigger
   an early callback later in the MD380's main() function to perform
   any late hooks that must be applied to function pointers
   initialized in the stock firmware.
*/
int main(void) {

  dmesg_init();
  
  md380_CPS_version[0] = 0;
  md380_CPS_version[1] = 0;
  md380_CPS_version[2] = 1;
  md380_CPS_version[3] = 1;
  /*
  RTC_TimeTypeDef RTC_TimeTypeTime;
  md380_RTC_GetTime(RTC_Format_BIN, &RTC_TimeTypeTime);
  printf("%d:%d:%d\n", RTC_TimeTypeTime.RTC_Hours,
                       RTC_TimeTypeTime.RTC_Minutes,
                       RTC_TimeTypeTime.RTC_Seconds);
  */
  //while (1) {}
	
     
  //Done with the blinking, so start the radio application.
  //printf("Starting main()\n");
  abort_to_mfgr_app();
}

