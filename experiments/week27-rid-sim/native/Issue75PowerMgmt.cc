// Own extension via public interfaces; original PR2 class/binary is preserved.
#include "rid_beacon/RidBeaconMgmt.h"
#include "inet/linklayer/common/MacAddressTag_m.h"
#include "inet/linklayer/ieee80211/mac/Ieee80211SubtypeTag_m.h"
#include "inet/physicallayer/wireless/common/contract/packetlevel/SignalTag_m.h"
#include "inet/physicallayer/wireless/common/base/packetlevel/FlatTransmitterBase.h"
#include "Issue75AttackMath.h"
#include <map>
#include <sstream>

using namespace inet::physicallayer;

class Issue75PowerMgmt : public RidBeaconMgmt {
    double selectedDbm=13;
    int sequence=0;
    std::string mode;
    std::map<int,issue75::Point> catalog;
    std::vector<int> schedule;
    cOutVector requested,index,delta,applied,attackClip,phyClip,error,target,nominalLog;

    void initialize(int stage) override {
        RidBeaconMgmt::initialize(stage);
        if (stage!=INITSTAGE_LOCAL) return;
        requested.setName("Requested PHY Power");index.setName("Power Packet Index");
        delta.setName("Attack Requested Delta");applied.setName("Attack Applied Delta");
        attackClip.setName("Attack Bound Clamped");phyClip.setName("Attack PHY Clamped");
        error.setName("Attack Compensation Error");target.setName("Attack Target RX");
        nominalLog.setName("Attack Nominal dBm");
        mode=par("attackMode").stdstringValue();
        if (mode!="position_only" && mode!="reference_rx0" && mode!="schedule_aware" && mode!="schedule_blind")
            throw cRuntimeError("Unknown declared attack knowledge");
        std::istringstream stream(par("receiverCatalog").stdstringValue());std::string entry;
        while (std::getline(stream,entry,';')) {
            for (char& c:entry) if (c==':' || c==',') c=' ';
            std::istringstream values(entry);int node;issue75::Point position;std::string extra;
            if (!(values>>node>>position[0]>>position[1]>>position[2]) || values>>extra || catalog.count(node))
                throw cRuntimeError("Invalid receiver catalog");
            catalog[node]=position;
        }
        if (catalog.empty() || !catalog.count(0)) throw cRuntimeError("Missing reference receiver");
        // The blind path NEVER reads observerSchedule, and its math helper has
        // no argument capable of receiving the defender's future selection.
        if (mode=="schedule_aware") {
            std::istringstream selection(par("observerSchedule").stdstringValue());int node;
            while (selection>>node) {
                if (!catalog.count(node)) throw cRuntimeError("Unknown scheduled receiver");
                schedule.push_back(node);
            }
            if (schedule.empty() || !selection.eof()) throw cRuntimeError("Invalid oracle schedule");
        }
    }

    bool fillRidMsg(const Ptr<RidBeaconFrame>& frame) override {
        RidBeaconMgmt::fillRidMsg(frame);
        const issue75::Point actual={frame->getPosX(),frame->getPosY(),frame->getPosZ()};
        frame->setPosX(actual[0]+par("claimOffsetX").doubleValueInUnit("m"));
        frame->setPosY(actual[1]+par("claimOffsetY").doubleValueInUnit("m"));
        frame->setPosZ(actual[2]+par("claimOffsetZ").doubleValueInUnit("m"));
        const issue75::Point claim={frame->getPosX(),frame->getPosY(),frame->getPosZ()};
        double change=0;int selected=-1;
        try {
            if (mode=="reference_rx0" || mode=="schedule_aware") {
                selected=mode=="reference_rx0" ? 0 : schedule[sequence%schedule.size()];
                change=issue75::compensation(actual,claim,catalog.at(selected));
            } else if (mode=="schedule_blind") {
                std::vector<issue75::Point> receivers;
                for (const auto& item:catalog) receivers.push_back(item.second);
                change=issue75::blindCompensation(actual,claim,receivers);
            }
            const double nominal=par("nominalDbm");
            const auto chosen=issue75::apply(nominal,change,par("rangeDb"),par("minimumDbm"),par("maximumDbm"));
            selectedDbm=chosen.power;
            delta.record(chosen.requestedDelta);applied.record(chosen.appliedDelta);
            attackClip.record(chosen.attackClamped);phyClip.record(chosen.phyClamped);
            error.record(chosen.error);target.record(selected);nominalLog.record(nominal);
        } catch (const std::exception& ex) {throw cRuntimeError("%s",ex.what());}
        auto *radio=getModuleFromPar<cModule>(par("radioModule"),this);
        check_and_cast<FlatTransmitterBase*>(radio->getSubmodule("transmitter"))->setPower(W(std::pow(10.,(selectedDbm-30.)/10.)));
        requested.record(selectedDbm);index.record(sequence++);
        return actual!=claim;
    }

    void sendManagementFrame(const char *name,const Ptr<Ieee80211MgmtFrame>& frame,int subtype,const MacAddress& destination) override {
        auto *outgoing=new Packet(name);
        outgoing->addTag<SignalPowerReq>()->setPower(W(std::pow(10.,(selectedDbm-30.)/10.)));
        outgoing->addTag<Ieee80211SubtypeReq>()->setSubtype(subtype);
        outgoing->addTag<MacAddressReq>()->setDestAddress(destination);
        outgoing->insertAtBack(frame);recvec.txPacketId.record(outgoing->getTreeId());sendDown(outgoing);
    }
};
Define_Module(Issue75PowerMgmt);
