/* Offline reference decoding only. Never used as proof/circuit admission policy. */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include "opendroneid.h"
static int nibble(char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
static void number(double v){if(isfinite(v))printf("%.8f",v);else printf("null");}
int main(void){
 char line[1024];
 while(fgets(line,sizeof(line),stdin)){
  size_t l=strcspn(line,"\r\n");uint8_t raw[3+25*ODID_PACK_MAX_MESSAGES];int ok=(l%2==0&&l/2<=sizeof(raw)&&l>=6);size_t n=l/2;
  if(ok)for(size_t i=0;i<n;i++){int a=nibble(line[2*i]),b=nibble(line[2*i+1]);if(a<0||b<0){ok=0;break;}raw[i]=(uint8_t)((a<<4)|b);}
  if(ok)ok=((raw[0]>>4)==15&&(raw[0]&15)<=2&&raw[1]==25&&raw[2]>=1&&raw[2]<=ODID_PACK_MAX_MESSAGES&&n==(size_t)(3+25*raw[2]));
  if(!ok){puts("{\"reference_decode_ok\":false,\"reason\":\"invalid_pack_shape_or_version\"}");continue;}
  ODID_MessagePack_encoded pack;memset(&pack,0,sizeof(pack));memcpy(&pack,raw,n);ODID_UAS_Data data;odid_initUasData(&data);
  int result=decodeMessagePack(&data,&pack);
  if(result!=ODID_SUCCESS){puts("{\"reference_decode_ok\":false,\"reason\":\"reference_rejected\"}");continue;}
  printf("{\"reference_decode_ok\":true,\"protocol_version\":%u,\"message_count\":%u,\"basic_id_valid\":%s,\"id_type\":%u,\"ua_type\":%u,\"id_hex\":\"",raw[0]&15,raw[2],data.BasicIDValid[0]?"true":"false",data.BasicID[0].IDType,data.BasicID[0].UAType);
  for(int i=0;i<ODID_ID_SIZE;i++)printf("%02x",(unsigned char)data.BasicID[0].UASID[i]);
  printf("\",\"location_valid\":%s,\"claimed_latitude\":",data.LocationValid?"true":"false");number(data.Location.Latitude);printf(",\"claimed_longitude\":");number(data.Location.Longitude);
  printf(",\"claimed_altitude_geo_m\":");number(data.Location.AltitudeGeo);printf(",\"claimed_altitude_baro_m\":");number(data.Location.AltitudeBaro);printf(",\"claimed_height_m\":");number(data.Location.Height);printf(",\"height_type\":%u,\"claimed_seconds_within_hour\":",data.Location.HeightType);number(data.Location.TimeStamp);
  printf(",\"system_valid\":%s,\"identity_verified\":false,\"physical_position_verified\":false}\n",data.SystemValid?"true":"false");
 }
 return 0;
}
