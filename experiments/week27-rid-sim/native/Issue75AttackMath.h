// Original mathematical adapter. No upstream implementation is copied.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace issue75 {
using Point = std::array<double,3>;
inline double distance(const Point& a,const Point& b) {
    return std::hypot(std::hypot(a[0]-b[0],a[1]-b[1]),a[2]-b[2]);
}
inline double compensation(const Point& actual,const Point& claim,const Point& receiver) {
    const double d=distance(actual,receiver),q=distance(claim,receiver);
    if (!std::isfinite(d) || !std::isfinite(q) || d<=1e-3 || q<=1e-3)
        throw std::invalid_argument("Nonfinite or near-zero compensation distance");
    return 20*std::log10(d/q);
}
inline double blindCompensation(const Point& actual,const Point& claim,const std::vector<Point>& receivers) {
    if (receivers.empty()) throw std::invalid_argument("Empty predeclared receiver prior");
    double delta=0;
    for (const auto& receiver:receivers) delta+=compensation(actual,claim,receiver);
    // A uniform prior over receiver coordinates, declared BEFORE observations.
    // This function cannot receive a selected receiver, schedule, or RX result.
    return delta/receivers.size();
}
struct Applied {
    double requestedDelta,appliedDelta,power,error;
    bool attackClamped,phyClamped;
};
inline Applied apply(double nominal,double requested,double bound,double minimum,double maximum) {
    if (!std::isfinite(nominal) || !std::isfinite(requested) || !std::isfinite(bound) || bound<0 ||
        !std::isfinite(minimum) || !std::isfinite(maximum) || minimum>maximum)
        throw std::invalid_argument("Invalid power constraints");
    const double bounded=std::clamp(requested,-bound,bound);
    const double power=std::clamp(nominal+bounded,minimum,maximum);
    return {requested,power-nominal,power,power-nominal-requested,bounded!=requested,power!=nominal+bounded};
}
}
