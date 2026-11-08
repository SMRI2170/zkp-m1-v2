"""GCS logging callback only. Does not detect spoofing or consume simulator truth."""


class SmokeAudit:
    def on_gcs_reports(self, data):
        # Upstream exposes only the first report's packet_id here. The RX/TX
        # vector audit must separately check physical packet correspondences.
        return {"log": {"packet_id": data["packet_id"],
                        "report_count": len(data["reports"]),
                        "claimed_timestamp_ms": data["rid_timestamp"],
                        "claimed_serial": data["serial_number"]}}
