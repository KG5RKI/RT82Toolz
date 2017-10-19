/*! \file usersdb.c
\brief There is the functionality
       which dmr id to the entry from the users.csv in flash reads
       the first line is the size im byte
*/

#include <stdlib.h>
#include <string.h>



#include "md380.h"
#include "usersdb.h"
#include "spiflash.h"
#include "syslog.h"
#include "etsi.h"

/* All user database data is accessed through this function.
 * This makes it easier to adapt to different kinds of sources.
 */
static char * getdata(char * dest, const char * src, int count) {
    md380_spiflash_read(dest, (long) src, count);
    return dest;
}


/* copies a line of text starting at in[] that is terminated
 * with a linefeed '\n' or '\0' to out[]. At most outsize characters
 * are written to out[] (including null terminator). Lines that
 * don't fit into out[] are truncated. out[] will always be
 * null terminated if outsize > 0.
 */
static void readline(char *out, const char *in, int outsize)
{
    if( outsize <= 0 ) return;
    getdata(out, in, outsize);
}

/* searches for a newline character starting at *p and returns
 * the pointer to the character following that newline
 */
static const char* next_line_ptr(const char* p) {

	//return (char*)(((long)(((long)p + 0x78) / 0x78)) * 0x78);
	//return (p + 0x78) - (((long)p + 0x78)%0x78);
	long pp = (long)p - 0x204003;
	long ppp = pp / 0x78;
	return (char*)(0x204003 + ((ppp + 1) * 0x78));
}

/* parse number as text and return its numerical value
 */
static long getfirstnumber(const char * p) {
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

static int find_dmr(char *outstr, long dmr_search,
	const char *dmr_begin, const char *dmr_end,
	int outsize)
{
	/* As long as there is at least one line of text between
	offsets dmr_begin and dmr_end... */
	long id = 0;
	while ( dmr_begin != dmr_end) {
		const char* dmr_test = next_line_ptr(dmr_begin + ((dmr_end - dmr_begin) / 2));
		if (dmr_test >= (char*)((int)dmr_end - (0x78 * 2))) { dmr_test = next_line_ptr(dmr_begin); }
		if (dmr_test >= (char*)((int)dmr_end - (0x78*2))) { dmr_test = dmr_begin; }
		id = getfirstnumber(dmr_test);
		//syslog_printf("\nID %d %08X", id, id);
		if (id == dmr_search) {
			//syslog_printf("\nFOUND %d %08X", id, id);
			readline(outstr, dmr_test, outsize);
			return 1;
		}
		if (dmr_search < id) {
			dmr_end = dmr_test;
		}
		else {
			dmr_begin = next_line_ptr(dmr_test);
		}
	}
	//syslog_printf("\nFailed. ID: %d %08X", dmr_search, dmr_search);
	return 0;
}


static int cacheUserID = 0;
static user_tdb cacheUser;

static int find_dmr_user(char *outstr, int dmr_search, const char *data, int outsize)
{
	/*dmr_search = 1106003;
	if (cacheUserID == dmr_search) {
		memcpy(outstr, &cacheUser, outsize);
		return 1;
	}
	for (int i = 0; i < 50; i++) {
		long id = getfirstnumber(data+(i*0x78));
		//syslog_printf("\n%d %08x", id, id);
		if (id == dmr_search) {
			syslog_printf("\nFound! %d", id);
			md380_spiflash_read(outstr, (long)data + (i * 0x78), outsize);
			cacheUserID = dmr_search;
			memcpy(&cacheUser, outstr, outsize);
			return 1;
		}
	}
	syslog_printf("\nNot Found! %d", dmr_search);
	return 0;*/
	//const long datasize = getfirstnumber(data);
	const long datasize = 100000 * 0x78;

    // filesize @ 20160420 is 2279629 bytes
    //          @ 20170213 is 2604591 bytes
    //if (datasize == 0 || datasize > 5242879)  // 5 Meg sanity limit
    //   return(0);

    const char *data_start = data;
    const char *data_end = data_start + datasize; // exclusive
    return find_dmr(outstr, dmr_search, data_start, data_end, outsize);
}

//#define _IS_TRAIL(buf, i, l) ((i > 0 && buf[i-1] == ',' && buf[i] == ' ') || (i < l && buf[i+1] == ',' && buf[i] == ' '))
//
//uint8_t get_dmr_user_field(uint8_t field, char *outstr, int dmr_search, int outsize)
//{
//    char buf[BSIZE];
//    uint8_t pos = 0;
//    uint8_t found = 0;
//    if ( find_dmr_user(buf, dmr_search, (void *) 0x100000, BSIZE) ) {
//        for (uint8_t i = 0; i < BSIZE; i++) {
//          if (buf[i] == 0 || pos >= outsize) {
//              break;
//          }
//          if (buf[i] == ',') {
//              found++;
//          }
//          if (found >= (field - 1) && buf[i] != ',' && !_IS_TRAIL(buf, i, BSIZE)) {
//              outstr[pos] = buf[i];
//              pos++;
//          }
//          if (found == field) {
//              break;
//          }
//        }
//    }
//    return pos;
//}

void usr_splitbuffer(user_t *up)
{
    char *cp = (char*)&up->buffer + 0x14 ;
    char *start = cp ;

	up->callsign = (char*)&up->buffer + 0x4;
	if (up->callsign[0] == '|') {
		up->callsign = up->callsign + 1;
		up->fUserType = 1;
	}
	else {
		up->fUserType = 0;
	}

	*((char*)(&up->buffer + 0x68)) = '\0';

	char* bb = 0xFF;
	int aa = 0;
    for(int fld=0;fld<8;fld++) {

        while(1) {
            if( *cp == 0 ) {
                break ;
            }
            if( *cp == ',' ) {
                *cp = 0 ;
                cp++ ;
                break ;
            }
            cp++ ;
        }
        
        switch(fld) {
            case 0 :
				up->firstname = (char*)&up->buffer + 0x68;
				up->name = start;
				aa = 0;
				for (bb = start; bb < 54 && *bb != '\0'; bb++) {
					up->firstname[aa++] = *bb;
					if (*bb == ' ' || *bb == ',') {
						up->firstname[aa] = '\0';
						break;
					}
				}
                break ;
            case 1 :
				up->place = start;
                break ;
            case 2 :
				up->state = start;
                break ;
            case 3 :
				
                break ;
            case 4 :
				up->country = start;
                break ;
            case 5 :
                break ;
            case 6 :
				
                break ;
        }
        
        start = cp ;
    }
}

int usr_find_by_dmrid( user_t *up, int dmrid )
{
	//syslog_printf("\nusrid: %d", dmrid);
    if( !find_dmr_user((char*)&up->buffer, dmrid, (void *) (0x204003), BSIZE) ) {
     
        usr_splitbuffer(up);
		
        return 0 ;
    }
    
    usr_splitbuffer(up);
    return 1 ;
}
