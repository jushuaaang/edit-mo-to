import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_common as pc
import plan_build as pb

def test_plan_build_reexports_shared_helpers():
    assert pb.sfx_cues is pc.sfx_cues and pb.US is pc.US and pb.check_plan is pc.check_plan

def test_us_is_integer_microseconds():
    assert pc.US(1) == 33333 and pc.US(30) == 1_000_000 and isinstance(pc.US(7), int)
