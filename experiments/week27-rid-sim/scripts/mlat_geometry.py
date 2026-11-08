"""Ideal circular-layout ambiguity: mathematical fixture, not RF output."""
import math


def circular_layout_counterexample():
    # Centered receiver square: all four receivers lie on one radius.
    receivers=[(-100,-100,0),(-100,100,0),(100,-100,0),(100,100,0)]
    actual=(80,0,38);scale=1.2;radius2=20000;horizontal2=80**2
    height2=scale*(radius2+horizontal2+38**2)-radius2-scale**2*horizontal2
    alternate=(scale*80,0,math.sqrt(height2));change=10*math.log10(scale)
    errors=[abs((13-20*math.log10(math.dist(actual,r)))-(13+change-20*math.log10(math.dist(alternate,r)))) for r in receivers]
    return dict(status='MATHEMATICAL_COUNTEREXAMPLE',receivers=4,distance_squared_scale=scale,power_change_db=change,
                max_rssi_difference_db=max(errors),both_heights_positive=True,
                scope='Ideal isotropic n=2 model, not a second INET RF run. Four co-circular receivers and unknown power leave a scale/height ambiguity even away from the center.')
