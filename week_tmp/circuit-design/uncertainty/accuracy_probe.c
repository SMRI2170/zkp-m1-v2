/* Pinned OpenDroneID v0 decoder cross-check; only accuracy metadata is printed. */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "opendroneid.h"
static int hex(char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
int main(void){char line[1024];while(fgets(line,sizeof(line),stdin)){
 size_t len=strcspn(line,"\r\n"),n=len/2;uint8_t b[228];int ok=len%2==0&&n>=3&&n<=sizeof(b);
 if(ok)for(size_t i=0;i<n;i++){int a=hex(line[i*2]),c=hex(line[i*2+1]);if(a<0||c<0){ok=0;break;}b[i]=(uint8_t)((a<<4)|c);}
 if(ok)ok=b[0]==0xf0&&b[1]==25&&b[2]>0&&b[2]<=9&&n==3+25*(size_t)b[2];
 if(!ok){puts("null");continue;}
 /* The historical pack decoder rejects duplicate Basic IDs. Audit the single
    Location message without claiming full-pack acceptance. Never modify it. */
 ODID_Location_encoded location;int found=0;
 for(size_t i=0;i<b[2];i++){uint8_t *m=b+3+25*i;if(m[0]==0x10){memcpy(&location,m,25);found++;}}
 ODID_Location_data d;memset(&d,0,sizeof(d));
 if(found!=1||decodeLocationMessage(&d,&location)!=ODID_SUCCESS){puts("null");continue;}
 printf("[%u,%u,%u,%u]\n",d.HorizAccuracy,d.VertAccuracy,d.BaroAccuracy,d.TSAccuracy);
}return 0;}
