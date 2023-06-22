from typing import List


def get_2_3rds_frontier_index(active_bonds: List[int]) -> int:
    t = len(active_bonds) * 2 // 3
    if len(active_bonds) % 3 == 0:
        t -= 1
    return t


def sort_bonds(active_bonds: List[int]) -> List[int]:
    """
    Sort bonds from the lowest to the highest
    @param active_bonds: list of node bonds
    @return: list of sorted bonds
    """
    if not active_bonds:
        return []
    # make sure we have ints
    active_bonds = [int(bond) for bond in active_bonds]
    active_bonds.sort()
    return active_bonds


def get_hard_bond_cap(active_bonds: List[int]) -> int:
    """
    Find the bond size the highest of the bottom 2/3rds active node bonds
    This is only for distribution of rewards
    @param active_bonds: list of node bonds
    @return: float amount of bond (in RUNE 8 decimals)
    """
    active_bonds = sort_bonds(active_bonds)
    if not active_bonds:
        return 0

    t = get_2_3rds_frontier_index(active_bonds)
    return active_bonds[t]


def get_effective_security_bond(active_bonds: List[int]) -> int:
    """
    Get the total bond of the bottom 2/3rds active nodes
    @param active_bonds: list of node bonds
    @return: float amount of bond (in RUNE 8 decimals)
    """
    active_bonds = sort_bonds(active_bonds)
    if not active_bonds:
        return 0

    t = get_2_3rds_frontier_index(active_bonds)

    amt = 0
    for i, bond in enumerate(active_bonds):
        if i <= t:
            amt += int(bond)
        else:
            break
    return amt
