from paper_live.feature_dataset import FeatureDatasetService

def test_snapshot_checksum_is_stable():
    row={"symbol":"005930","score":80.0,"rank":1}
    assert FeatureDatasetService.checksum(row)==FeatureDatasetService.checksum(dict(reversed(row.items())))
