package issue70power;

import uav_rid.rid_beacon.RidBeaconMgmt;
import uav_rid.rid_host.DroneHost;
import inet.physicallayer.wireless.ieee80211.packetlevel.Ieee80211DimensionalTransmitter;

simple Issue70PowerMgmt extends RidBeaconMgmt
{
    parameters:
        @class(Issue70PowerMgmt);
        string powerModel = default("fixed");
        double nominalDbm = default(13);
        double rangeDb = default(3);
        double maxStepDb = default(2);
        double minimumDbm = default(-80);
        double maximumDbm = default(23);
        double attackN = default(2);
        double claimOffsetX @unit(m) = default(0m);
        double claimOffsetY @unit(m) = default(0m);
        double claimOffsetZ @unit(m) = default(0m);
        double referenceX @unit(m) = default(100m);
        double referenceY @unit(m) = default(100m);
        double referenceZ @unit(m) = default(2m);
}

module Issue70PowerHost extends DroneHost
{
    parameters:
        wlan[0].mgmt.typename = "Issue70PowerMgmt";
        wlan[0].radio.transmitter.typename = "Issue70AuditedTransmitter";
}

module Issue70AuditedTransmitter extends Ieee80211DimensionalTransmitter
{
    parameters:
        @class(Issue70AuditedTransmitter);
}
