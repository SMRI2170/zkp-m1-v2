"""Explicit WGS84 to local ENU adapter; geometric normalization, not position authenticity."""
import math

class NotEvaluable(ValueError):pass

def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def latlon(p):
    if not finite(p.get('latitude')) or not -90<=p['latitude']<=90:raise NotEvaluable('LATITUDE_MISSING_OR_INVALID')
    if not finite(p.get('longitude')) or not -180<=p['longitude']<=180:raise NotEvaluable('LONGITUDE_MISSING_OR_INVALID')

def ecef(latitude,longitude,height):
    latlon(dict(latitude=latitude,longitude=longitude))
    if not finite(height):raise NotEvaluable('ALTITUDE_MISSING')
    phi,lam=map(math.radians,(latitude,longitude));a=6378137.;e2=6.6943799901413165e-3
    n=a/math.sqrt(1-e2*math.sin(phi)**2)
    return ((n+height)*math.cos(phi)*math.cos(lam),(n+height)*math.cos(phi)*math.sin(lam),(n*(1-e2)+height)*math.sin(phi))

def enu(p,origin,height):
    latlon(p);latlon(origin)
    x,y,z=ecef(p['latitude'],p['longitude'],height);a,b,c=ecef(origin['latitude'],origin['longitude'],origin.get('altitude_m',0.))
    x-=a;y-=b;z-=c;phi,lam=map(math.radians,(origin['latitude'],origin['longitude']))
    return (-math.sin(lam)*x+math.cos(lam)*y,-math.sin(phi)*math.cos(lam)*x-math.sin(phi)*math.sin(lam)*y+math.cos(phi)*z,math.cos(phi)*math.cos(lam)*x+math.cos(phi)*math.sin(lam)*y+math.sin(phi)*z)

def normalize_geometry(receiver,claim,origin,mode,*,radius_multiplier=1,projection_allowance_m=None):
    """Returns cm box centers/radii. External policy must approve the chosen assumptions.

    In 2D, project lat/lon onto WGS84 ellipsoid; do not invent measured heights.
    A fixed frame's projection allowance must be supplied, not silently set to zero.
    3D requires explicitly verified common WGS84 ellipsoid datum and both vertical radii.
    """
    if mode not in [2,3]:raise NotEvaluable('MODE_INVALID')
    if not finite(radius_multiplier) or radius_multiplier<1:raise NotEvaluable('RADIUS_MULTIPLIER_INVALID')
    if not finite(projection_allowance_m) or projection_allowance_m<0:raise NotEvaluable('PROJECTION_ALLOWANCE_MISSING')
    for p in [receiver,claim]:
        latlon(p)
        if not finite(p.get('horizontal_accuracy_m')) or p['horizontal_accuracy_m']<0:raise NotEvaluable('HORIZONTAL_ACCURACY_MISSING')
    if mode==3:
        for p in [receiver,claim,origin]:
            if p.get('altitude_datum')!='WGS84_ELLIPSOID' or p.get('datum_verified') is not True:raise NotEvaluable('COMMON_VERTICAL_DATUM_UNVERIFIED')
            if not finite(p.get('altitude_m')):raise NotEvaluable('ALTITUDE_MISSING')
        for p in [receiver,claim]:
            if not finite(p.get('vertical_accuracy_m')) or p['vertical_accuracy_m']<0:raise NotEvaluable('VERTICAL_ACCURACY_MISSING')
    result={'mode':mode,'frame_projection_is_external':True,'error_radii_are_assumed_not_true_error':True}
    for label,p in [('receiver',receiver),('claim',claim)]:
        point=enu(p,origin,p['altitude_m'] if mode==3 else 0.)
        center=[round(v*100)+(1<<19) for v in point]
        if mode==2:center[2]=1<<19 # inactive z coordinate, not a measured zero altitude
        if any(v<0 or v>=(1<<20) for v in center):raise NotEvaluable('POINT_OUTSIDE_LOCAL_FRAME')
        h=math.ceil((p['horizontal_accuracy_m']*radius_multiplier+projection_allowance_m)*100)+1 # outward radius plus cm quantization
        v=math.ceil((p['vertical_accuracy_m']*radius_multiplier+projection_allowance_m)*100)+1 if mode==3 else 0
        if max(h,v)>=(1<<20):raise NotEvaluable('ERROR_OUTSIDE_CIRCUIT_RANGE')
        result[label]=dict(center_cm=center,axis_error_cm=[h,h,v])
    return result
