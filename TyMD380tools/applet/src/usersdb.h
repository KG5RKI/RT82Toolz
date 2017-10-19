
#ifndef _USERSDB_H
#define _USERSDB_H

#define BSIZE 0x78

typedef struct {
	uint32_t id;
	char callsign[16];
	char data[0x64];
} user_tdb;

typedef struct {
	user_tdb buffer;
    uint32_t id ;
    char *callsign ;
    char *firstname ;
    char *name ;
    char *place ;
    char *state ;
    char *country ;
	char fUserType;
} user_t ;

/**
 * lookup the a user given their ID (dmr_search) in the database.
 * The function returns 1 for success and 0 for "not found".
 */
int usr_find_by_dmrid( user_t *up, int dmrid );

#endif
