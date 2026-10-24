"""End-to-end check of ProblemLoader + UAV instance loading, making sure the
changes do not break UAV."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kares_workflow.problem_loader import ProblemLoader

# UAV regression test
print("=== UAV regression ===")
pl = ProblemLoader("uav_firefighting")
insts = pl.get_instances()
print(f"  found {len(insts)} instances")
print(f"  instances_dir = {pl.instances_dir}")
print(f"  instance_pattern = {pl.instance_pattern}")
print(f"  interface_contract length = {len(pl.interface_contract)} chars")
print(f"  baseline_path = {pl.baseline_path}")
if insts:
    print(f"  first instance = {insts[0]}")
    print(f"  last instance = {insts[-1]}")

print("\n=== Summary of all 5 problems ===")
for s in ["uav_firefighting", "cvrp_set_e", "cvrp_set_f", "cvrp_set_m", "cvrp_set_p"]:
    pl = ProblemLoader(s)
    insts = pl.get_instances()
    has_contract = "yes" if "fitness_large" in pl.interface_contract or "3000" in pl.interface_contract else "no"
    print(f"  {s:20s} instances={len(insts):3d}  baseline={pl.baseline_path.split('/')[-1]}  "
          f"custom_contract={has_contract}")
