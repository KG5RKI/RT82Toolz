/*! \file dmr.c
  \brief DMR Hook functions.

  This module hooks some of the DMR packet handler functions,
  in order to extend the functionality of the radio.  Ideally,
  we'd like to use just the hooks, but for the time-being some
  direct patches and callbacks are still necessary.
 
 * glue layer 
*/

#define CONFIG_DMR

#define NETMON
#define DEBUG

#include "dmr.h"

#include <string.h>

#include "md380.h"
#include "printf.h"
#include "dmesg.h"
#include "version.h"
#include "tooldfu.h"
#include "config.h"
#include "radiostate.h"
#include "amenu_set_tg.h"
#include "codeplug.h"

#define PRINT
#define PRINTHEX
#define NMPRINT

/* global Bufferspace to transfer data*/
//char DebugLine1[30];
//char DebugLine2[160];  // only for debug normal is 80

//int g_dst;  // transferbuffer users.csv
//int g_dst_is_group;
//int g_src;

// Table 6.1: Data Type information element definitions

// unused?
enum data_type {
    PI_HDR = 0,
    VOICE_LC_HDR = 1,
    TERM_WITH_LC = 2,
    CSBK = 3,
    MBC_HDR = 4,
    MBC_CONT = 5,
    DATA_HDR = 6,
    RATE_1_2_DATA = 7,
    RATE_3_4_DATA = 8,
    IDLE = 9,            
    RATE_1_DATA = 10            
};

typedef struct pkt {
    uint16_t hdr ;
    uint8_t b0 ;
    uint8_t b1 ;
    uint8_t unk1 ;
    adr_t dst ;
    adr_t src ;    
} pkt_t;

// 9.3.18 SAP identifier (SAP)
enum sap_t {
    UDT = 0,
    TCP = 1,
    UDP = 2,
    IP = 3,
    ARP = 4,
    PPD = 5,
    SD = 0xa, // Short Data 
};

typedef struct raw_sh_hdr {
    uint8_t b0 ;
    // carefull bitfields are dangerous.
    uint8_t sap : 4 ;  // bit 7..4 (reverse from normal)
    uint8_t ab2 : 4 ;  // bit 3..0 (reverse from normal)
    adr_t dst ;
    adr_t src ;    
    uint8_t sp : 3 ; 
    uint8_t dp : 3 ;
    uint8_t sf : 2 ; // S & F
} raw_sh_hdr_t;

// unvalidated.
void dump_raw_short_header( const char *tag, raw_sh_hdr_t *pkt )
{
    NMPRINT("%s(sap=%d,src=%d,dst=%d,sp=%d,dp=%d) ", tag, pkt->sap, get_adr(pkt->src), get_adr(pkt->dst), pkt->sp, pkt->dp );
    PRINT("%s(sap=%d,src=%d,dst=%d,sp=%d,dp=%d)\n", tag, pkt->sap, get_adr(pkt->src), get_adr(pkt->dst), pkt->sp, pkt->dp );
}

typedef struct lc_hdr {
    uint8_t pf_flco ;    
    uint8_t fid ;
} lc_hdr_t ;

// Control Signalling Block (CSBK) PDU
// TODO: finish / validate
typedef struct mbc {
    uint8_t lb_pf_csbko ;    
    uint8_t fid ;    
    union {
        struct {
            //uint8_t sap ; // ??
            adr_t dst ;
            adr_t src ;                
        } sms ;
    } ;	
} mbc_t ;

inline uint8_t get_csbko( mbc_t *mbc )
{
    return mbc->lb_pf_csbko & 0x3f ;
}


// unvalidated
void dump_mbc( mbc_t *mbc )
{
    uint8_t csbko = get_csbko(mbc);
    uint8_t fid = mbc->fid ;
    
    PRINT("csbko=%02x fid=%02x ", csbko, fid);
    PRINT("src=%d dst=%d\n",get_adr(mbc->sms.src),get_adr(mbc->sms.dst));
}

//void dump_data( data_hdr_t *data )
//{
//    //TODO: print DPF (6.1.1))
//    // 9.3.17 from part 1
//    int sap = get_sap(data);
//    int blocks = get_blocks(data);
//    int dpf = get_dpf(data);
//    PRINT("sap=%d %s dpf=%d %s src=%d dst=%d %d\n", sap, sap_to_str(sap), dpf, dpf_to_str(dpf), get_adr(data->src),get_adr(data->dst), blocks);
//}

void dumpraw_lc(uint8_t *pkt)
{
    uint8_t tp = (pkt[1] >> 4) ;
    PRINT("type=%d ", tp );
    
    lc_t *lc = (lc_t*)(pkt + 2);
    dump_full_lc(lc);

    uint8_t flco = get_flco(lc);
    
	//if not a group call or private call type
    if( flco != 0 && flco != 3 ) { 
        PRINTHEX(pkt,14);        
        PRINT("\n");
    }
}

// unvalidated
void dumpraw_mbc(uint8_t *pkt)
{
    uint8_t tp = (pkt[1] >> 4) ;
    PRINT("type=%d ", tp );

    mbc_t *mbc = (mbc_t*)(pkt + 2);
    dump_mbc(mbc);
}

//void dumpraw_data(uint8_t *pkt)
//{
//    uint8_t tp = (pkt[1] >> 4) ;
//    PRINT("type=%d ", tp );
//
//    data_hdr_t *data = (data_hdr_t*)(pkt + 2);
//    dump_data(data);
//}

void dmr_CSBK_handler_hook(uint8_t *pkt)
{
//    PRINTRET();
//    PRINT("CSBK: ");
//    PRINTHEX(pkt,14);
//    PRINT("\n");
	lc_t *lc = (void*)(pkt + 2);

	int src = get_adr(lc->src);
	int dst = get_adr(lc->dst);
	int flco = get_flco(lc);

	if (ad_hoc_talkgroup) {
		lc->dst = set_adr(ad_hoc_talkgroup);
	}

    dmr_CSBK_handler(pkt);
}


void *dmr_call_end_hook(uint8_t *pkt)
{
	/* This hook handles the dmr_contact_check() function, calling
	back to the original function where appropriate.

	pkt points to something like this:

	                /--dst-\ /--src-\
       08 2a 00 00 00 00 00 63 30 05 54 7c 2c 36

	In a clean, simplex call this only occurs once, but on a
	real-world link, you'll find it called multiple times at the end
	of the packet.
	*/
	{
		lc_t *data = (void*)(pkt + 2);
		rst_term_with_lc(data);
	}

	//Forward to the original function.
	return dmr_call_end(pkt);
}

extern void checkAdHocTG();

int adhoc_tg_hook(int dmr_src, int dmr_dst, uint8_t *buffer) {
	checkAdHocTG();
	return sub_805F562(dmr_src, (ad_hoc_talkgroup ? ad_hoc_talkgroup : dmr_dst), buffer);
}

void *dmr_call_start_hook(uint8_t *pkt)
{
//    PRINTRET();
//    PRINTHEX(pkt,11);
//    PRINT("\n");

    /* This hook handles the dmr_contact_check() function, calling
       back to the original function where appropriate.

       It is called several times per call, presumably when the
       addresses are resent for late entry.  If you need to trigger
       something to happen just once per call, it's better to put that
       in dmr_call_end_hook().

       pkt looks like this:

       overhead
       /    /         /--dst-\ /--src-\
       08 1a 00 00 00 00 00 63 30 05 54 73 e3 ae
       10 00 00 00 00 00 00 63 30 05 54 73 2c 36
     */

//    //Destination adr as Big Endian.
//    int dst = (pkt[7] |
//            (pkt[6] << 8) |
//            (pkt[5] << 16));
//
//    int src = (pkt[10] |
//            (pkt[9] << 8) |
//            (pkt[8] << 16));
//            
//    int groupcall = (pkt[2] & 0x3F) == 0;
    {
        lc_t *data = (void*)(pkt + 2);

        rst_voice_lc_header( data );
    }

    //  OSSemPend(debug_line_sem, 0, &err);
    //
    //printf("Call start %d -> %d\n", src,dst);
    //  sprintf(DebugLine1, "%d -> %d", src, dst );

    //  if( find_dmr_user(DebugLine2, src, (void *) 0x100000, 80) == 0){
    //    sprintf(DebugLine2, ",ID not found,in users.csv,see README.md,on Github");   // , is line seperator ;)
    //  }

    //  OSSemPost(debug_line_sem);

//    int primask = OS_ENTER_CRITICAL();
//    g_dst = dst;
//    g_dst_is_group = groupcall;
//    g_src = src;
//    OS_EXIT_CRITICAL(primask);

    //Forward to the original function.
    return dmr_call_start(pkt);
}



void *dmr_handle_data_hook(char *pkt, int len)
{
	//    PRINTRET();
	//    PRINTHEX(pkt,len);
	//    PRINT("\n");

	/* This hook handles the dmr_contact_check() function, calling
	back to the original function where appropriate.

	Packes are up to twelve bytes, but they are always preceeded by
	two bytes of C5000 overhead.
	*/

	//    //Turn on the red LED to know that we're here.
	//    red_led(1);

	//    printf("Data:       ");
	//    printhex(pkt, len + 2);
	//    printf("\n");

	{
		data_blk_t *data = (void*)(pkt + 2);
		rst_data_block(data, len);
	}

	//Forward to the original function.
	return dmr_handle_data(pkt, len);
}

/* These Motorola Basic Privacy keys are sampled manually from silent
   frames in the air, so they are imperfect and likely contain flipped
   bits.  A better method would be to extract the complete sequence from
   either motorola firmware or automatically fetch them from the first
   frame of a transmission.
 */
const char* getmotorolabasickey(int i){
  switch(i&0xFF){
  case 1:
    return "\x1F\x00\x1F\x00\x1F\x00\x00";
  case 2:
    return "\xE3\x00\xE3\x00\xE3\x00\x01";
  case 3:
    return "\xFC\x00\xFC\x00\xFC\x00\x01";
  case 4:
    return "\x25\x03\x25\x03\x25\x03\x00";
  case 5:
    return "\x3A\x03\x3A\x03\x3A\x03\x00";
  case 6:
    return "\xC6\x03\xC6\x03\xC6\x03\x01";
  case 7:
    return "\xD9\x03\xD9\x03\xD9\x03\x01";
  case 8:
    return "\x4A\x05\x4A\x05\x4A\x05\x00";
  case 9:
    return "\x55\x05\x55\x05\x55\x05\x00";
  case 10:
    return "\xA9\x05\xA9\x05\xA9\x05\x01";
  case 11:
    return "\xB6\x05\xB6\x05\xB6\x05\x01";
  case 12:
    return "\x6F\x06\x6F\x06\x6F\x06\x00";
  case 13:
    return "\x70\x06\x70\x06\x70\x06\x00";
  case 14:
    return "\x8C\x06\x8C\x06\x8C\x06\x01";
  case 15:
    return "\x93\x06\x93\x06\x93\x06\x01";
  case 16:
    return "\x26\x08\x26\x18\x26\x18\x00";
//List gets sparse after here.
  case 32:
    return "\x4B\x08\x4B\x28\x4B\x28\x00";
  case 55:
    return "\xB4\x03\xB4\x33\xB4\x33\x01";
  case 63:
    return "\xFE\x06\xFE\x36\xFE\x36\x01";
  case 64:
    return "\x2B\x09\x2B\x49\x2B\x49\x00";
  case 69:
    return "\x11\x0A\x11\x4A\x11\x4A\x00";
  case 85:
    return "\x37\x02\x37\x52\x37\x52\x00";
  case 100:
    return "\x45\x02\x45\x62\x45\x62\x00";
  case 101:
    return "\x5A\x02\x5A\x62\x5A\x62\x00";
  case 114:
    return "\xA5\x09\xA5\x79\xA5\x79\x01";
  case 127:
    return "\xD5\x0F\xD5\x7F\xD5\x7F\x01";
  case 128:
    return "\x4D\x09\x4D\x89\x4D\x89\x00";
  case 144:
    return "\x6B\x01\x6B\x91\x6B\x91\x00";
  case 170:
    return "\xAF\x04\xAF\xA4\xAF\xA4\x01";
  case 176:
    return "\x20\x09\x20\xB9\x20\xB9\x00";
  case 192:
    return "\x66\x00\x66\xC0\x66\xC0\x00";
  case 200:
    return "\x2C\x05\x2C\xC5\x2C\xC5\x00";
  case 208:
    return "\x84\x00\x84\xD0\x84\xD0\x01";
  case 240:
    return "\x0B\x00\x0B\xF0\x0B\xF0\x00";
  case 250:
    return "\xA2\x05\xA2\xF5\xA2\xF5\x01";
  case 255:
    return "\x98\x06\x98\xF6\x98\xF6\x01";
  default:
    printf("\nERROR: Motorola Basic Key %d is unknown.\n",i);
    return "ERROR MESSAGE";
  }
}

/* This hook intercepts calls to aes_cipher(), which is used to turn
   the 128-bit Enhanced Privacy Key into a 49-bit sequence that gets
   XORed with the audio before transmission and after reception.
   
   By changing the output to match Motorola's Basic Privacy, we can
   patch the MD380 to be compatible with a Motorola network.
   
   The function is also used for two startup checks, presumably
   related to the ALPU-MP copy protection chip.  If those checks are
   interfered with, the radio will boot to a blank white screen.
 */
char *aes_cipher_hook(char *pkt){
  char *res;
  int i, sum=0;
  
  //Sum all the the first byte, looking for near-empty keys.
  for(i=1;i<16;i++)
    sum|=pkt[i];
  if(!sum){
    memcpy(pkt,getmotorolabasickey(pkt[0]),7);
    return pkt;
  }
  
  /* The key has more than its least-significant byte set, so we'll
     use the original Tytera algorithm.  At some point, it might make
     sense to replace this with proper crypto, rather than XOR.
  */
  res=aes_cipher(pkt);
  return res;
}