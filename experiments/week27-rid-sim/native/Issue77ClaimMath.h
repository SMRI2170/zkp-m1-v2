// Own claim geometry, independent of the selected observer schedule.
#pragma once
#include "Issue75AttackMath.h"
#include <string>

namespace issue77 {
using issue75::Point;
inline Point claim(const Point& p,const Point& anchor,const std::string& direction,double delta) {
    if (direction!="x" && direction!="toward" && direction!="away" && direction!="tangent" && direction!="vertical" && direction!="equidistant")
        throw std::invalid_argument("Unknown claim direction");
    if (!std::isfinite(delta) || delta<0) throw std::invalid_argument("Invalid displacement");
    if (delta==0) return p;
    Point q=p;
    if (direction=="x") q[0]+=delta;
    else if (direction=="vertical") q[2]+=delta;
    else {
        const double x=p[0]-anchor[0],y=p[1]-anchor[1],rho=std::hypot(x,y);
        if (!std::isfinite(rho) || rho<1e-6) throw std::invalid_argument("Undefined horizontal direction");
        if (direction=="equidistant") {
            if (delta>2*rho) throw std::invalid_argument("Requested chord exceeds diameter");
            const double theta=2*std::asin(delta/(2*rho));
            q[0]=anchor[0]+x*std::cos(theta)-y*std::sin(theta);
            q[1]=anchor[1]+x*std::sin(theta)+y*std::cos(theta);
        } else {
            const double ux=direction=="tangent" ? -y/rho : x/rho;
            const double uy=direction=="tangent" ? x/rho : y/rho;
            const double sign=direction=="toward" ? -1 : 1;
            q[0]+=sign*delta*ux;q[1]+=sign*delta*uy;
        }
    }
    for (double v:q) if (!std::isfinite(v) || v<0 || v>500) throw std::invalid_argument("Claim outside declared [0,500]m simulation box");
    return q;
}
}
