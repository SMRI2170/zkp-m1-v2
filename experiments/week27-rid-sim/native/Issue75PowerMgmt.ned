package issue70power;

import uav_rid.rid_host.DroneHost;

simple Issue75PowerMgmt extends Issue70PowerMgmt
{
    parameters:
        @class(Issue75PowerMgmt);
        string attackMode = default("position_only");
        string receiverCatalog;
        string observerSchedule = default("");
}

module Issue75PowerHost extends DroneHost
{
    parameters:
        wlan[0].mgmt.typename = "Issue75PowerMgmt";
        wlan[0].radio.transmitter.typename = "Issue70AuditedTransmitter";
}
