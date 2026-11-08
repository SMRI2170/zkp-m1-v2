// Original adapter using public INET/upstream interfaces. No upstream source
// is vendored or patched. Built binaries remain local research artifacts.
#include "rid_beacon/RidBeaconMgmt.h"
#include "inet/linklayer/common/MacAddressTag_m.h"
#include "inet/linklayer/ieee80211/mac/Ieee80211SubtypeTag_m.h"
#include "inet/physicallayer/wireless/common/contract/packetlevel/SignalTag_m.h"
#include "inet/physicallayer/wireless/common/base/packetlevel/FlatTransmitterBase.h"
#include "inet/physicallayer/wireless/ieee80211/packetlevel/Ieee80211DimensionalTransmitter.h"
#include <algorithm>

using namespace inet::physicallayer;

class Issue70PowerMgmt : public RidBeaconMgmt {
    double selectedDbm = 13, stateDb = 0;
    int sequence = 0;
    cOutVector requested, index;

    void initialize(int stage) override {
        RidBeaconMgmt::initialize(stage);
        if (stage == INITSTAGE_LOCAL) {
            requested.setName("Requested PHY Power");
            index.setName("Power Packet Index");
        }
    }

    bool fillRidMsg(const Ptr<RidBeaconFrame>& frame) override {
        // Preserve the baseline serial, timestamp and velocity before changing
        // only position. This avoids the legacy static spoofer's ID side effect.
        RidBeaconMgmt::fillRidMsg(frame);
        const double x = frame->getPosX(), y = frame->getPosY(), z = frame->getPosZ();
        frame->setPosX(x + par("claimOffsetX").doubleValueInUnit("m"));
        frame->setPosY(y + par("claimOffsetY").doubleValueInUnit("m"));
        frame->setPosZ(z + par("claimOffsetZ").doubleValueInUnit("m"));
        const double nominal = par("nominalDbm"), bound = par("rangeDb");
        const std::string model = par("powerModel").stdstringValue();
        double change = 0;
        if (model == "uniform") {
            change = uniform(-bound, bound, 1); // dedicated RNG stream
        } else if (model == "slew") {
            const double step = par("maxStepDb");
            stateDb = std::clamp(stateDb + uniform(-step, step, 1), -bound, bound);
            change = stateDb;
        } else if (model == "adaptive") {
            const double ax = par("referenceX"), ay = par("referenceY"), az = par("referenceZ");
            const double d = std::hypot(std::hypot(x-ax, y-ay), z-az);
            const double q = std::hypot(std::hypot(frame->getPosX()-ax, frame->getPosY()-ay), frame->getPosZ()-az);
            if (d <= 0 || q <= 0) throw cRuntimeError("Zero reference distance");
            change = std::clamp(10 * double(par("attackN")) * std::log10(d/q), -bound, bound);
        } else if (model == "alternating") {
            change = sequence % 2 == 0 ? 0 : -93; // physical delivery unit experiment
        } else if (model != "fixed") {
            throw cRuntimeError("Unknown power model");
        }
        selectedDbm = std::clamp(nominal + change, double(par("minimumDbm")), double(par("maximumDbm")));
        const W watts(std::pow(10.0, (selectedDbm - 30.0) / 10.0));
        auto *radio = getModuleFromPar<cModule>(par("radioModule"), this);
        auto *transmitter = check_and_cast<FlatTransmitterBase*>(radio->getSubmodule("transmitter"));
        // The INET parameter is immutable at runtime. Do not weaken that
        // control: the packet's SignalPowerReq is the operative request.
        transmitter->setPower(watts);
        requested.record(selectedDbm);
        index.record(sequence++);
        return x != frame->getPosX() || y != frame->getPosY() || z != frame->getPosZ();
    }

    void sendManagementFrame(const char *name, const Ptr<Ieee80211MgmtFrame>& frame,
                             int subtype, const MacAddress& destination) override {
        // Attach the power to this Packet, so queued frames cannot accidentally
        // use the power selected for a later beacon.
        auto *outgoing = new Packet(name);
        outgoing->addTag<SignalPowerReq>()->setPower(W(std::pow(10.0, (selectedDbm-30.0)/10.0)));
        outgoing->addTag<Ieee80211SubtypeReq>()->setSubtype(subtype);
        outgoing->addTag<MacAddressReq>()->setDestAddress(destination);
        outgoing->insertAtBack(frame);
        recvec.txPacketId.record(outgoing->getTreeId());
        sendDown(outgoing);
    }
};
Define_Module(Issue70PowerMgmt);

class Issue70AuditedTransmitter : public Ieee80211DimensionalTransmitter {
    mutable cOutVector physicalPacket, physicalPower, tagPresent;
    void initialize(int stage) override {
        Ieee80211DimensionalTransmitter::initialize(stage);
        if (stage == INITSTAGE_LOCAL) {
            physicalPacket.setName("PHY Packet ID");
            physicalPower.setName("PHY Power dBm");
            tagPresent.setName("PHY Power Tag Present");
            // createTransmission is invoked in RadioMedium's context. Bind
            // vector provenance now, during this transmitter's initialization.
            physicalPacket.registerVector();
            physicalPower.registerVector();
            tagPresent.registerVector();
        }
    }
    const ITransmission *createTransmission(const IRadio *radio, const Packet *packet, simtime_t start) const override {
        auto *transmission = Ieee80211DimensionalTransmitter::createTransmission(radio, packet, start);
        physicalPacket.record(packet->getTreeId());
        physicalPower.record(10 * std::log10(computeTransmissionPower(packet).get()) + 30);
        tagPresent.record(packet->findTag<SignalPowerReq>() != nullptr ? 1 : 0);
        return transmission;
    }
};
Define_Module(Issue70AuditedTransmitter);
