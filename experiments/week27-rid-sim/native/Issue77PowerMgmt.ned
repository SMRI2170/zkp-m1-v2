package issue70power;
import uav_rid.rid_host.DroneHost;

simple Issue77PowerMgmt extends Issue75PowerMgmt
{
    parameters:
        @class(Issue77PowerMgmt);
        string claimDirection = default("x");
        double claimDistance @unit(m) = default(0m);
}

module Issue77PowerHost extends DroneHost
{
    parameters:
        wlan[0].mgmt.typename = "Issue77PowerMgmt";
        wlan[0].radio.transmitter.typename = "Issue70AuditedTransmitter";
}
