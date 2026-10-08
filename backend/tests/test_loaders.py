import pandas as pd
import pytest

from ml.backend_models.datasets.loaders import load_and_map, split_for_training

COLS = [" Source IP", " Source Port", " Destination IP", " Destination Port", " Protocol",
        " Flow Duration", " Total Fwd Packets", " Total Backward Packets",
        "Total Length of Fwd Packets", " Total Length of Bwd Packets", " Label"]


def _row(label, protocol=6, duration=2_000_000, dport=80, fwd=10, bwd=10, fbytes=1000, bbytes=500):
    return ["10.0.0.1", 40000, "10.0.0.2", dport, protocol, duration, fwd, bwd, fbytes, bbytes, label]


@pytest.fixture
def csv_dir(tmp_path):
    rows = [
        _row("BENIGN"),
        _row("DoS Hulk", protocol=17),
        _row("PortScan", protocol=1, duration=0),
        _row("Infiltration"),
        _row("Bot"),                          # unmapped label -> dropped
        _row("BENIGN", duration=float("inf")),  # Infinity -> dropped
    ]
    pd.DataFrame(rows, columns=COLS).to_csv(tmp_path / "flows.csv", index=False)
    return str(tmp_path)


def test_maps_fields_and_drops_bad_rows(csv_dir):
    vectors = load_and_map(csv_dir)
    assert [v.label for v in vectors] == ["normal", "ddos", "port_scan", "exfiltration"]
    normal = vectors[0]
    assert normal.protocol == "TCP" and normal.duration == 2.0
    assert normal.byte_count == 1500 and normal.packet_count == 20 and normal.packet_rate == 10.0
    assert (normal.src_port, normal.dst_port) == (40000, 80)
    assert vectors[1].protocol == "UDP" and vectors[2].protocol == "ICMP"


def test_zero_duration_does_not_divide_by_zero(csv_dir):
    scan = load_and_map(csv_dir)[2]
    assert scan.duration == 0.0 and scan.packet_rate > 0


def test_split_for_training(csv_dir):
    vectors = load_and_map(csv_dir)
    multi, novelty = split_for_training(vectors)
    assert len(multi) == 4 and [v.label for v in novelty] == ["normal"]


def test_missing_csvs_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_and_map(str(tmp_path))
