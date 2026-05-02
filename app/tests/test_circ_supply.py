from lib.constants import RUNE_IDEAL_SUPPLY, RUNE_BURNT_ADR_12, ADR23_MAX_SUPPLY_PATCH_DELTA_RUNE
from lib.utils import recursive_asdict
from models.circ_supply import RuneCirculatingSupply


def test_rune_circulating_supply_burn_breakdown():
    supply = RuneCirculatingSupply(
        total=361_151_059,
        maximum=359_651_059,
        holders={},
    )

    assert supply.killed_switched == 13_948_941
    assert supply.adr12_burnt_rune == RUNE_BURNT_ADR_12
    assert supply.adr23_burnt_rune == 64_900_000
    assert supply.total_burned_rune == (
        supply.killed_switched
        + supply.adr12_burnt_rune
        + supply.adr23_burnt_rune
    )
    assert supply.burnt_rune_from_income == RUNE_IDEAL_SUPPLY - supply.maximum - ADR23_MAX_SUPPLY_PATCH_DELTA_RUNE


def test_rune_circulating_supply_income_burn_excludes_adr23_patch_delta():
    supply = RuneCirculatingSupply(
        total=361_151_059,
        maximum=359_651_059,
        holders={},
    )

    assert supply.burnt_rune_from_income == 2_272_676


def test_rune_circulating_supply_serialization_uses_adr_burn_names():
    supply = RuneCirculatingSupply(
        total=361_151_059,
        maximum=359_651_059,
        holders={},
    )

    plain = recursive_asdict(supply, add_properties=True)
    legacy_key = '_'.join(('lending', 'burnt', 'rune'))

    assert plain['adr12_burnt_rune'] == RUNE_BURNT_ADR_12
    assert plain['adr23_burnt_rune'] == 64_900_000
    assert legacy_key not in plain


