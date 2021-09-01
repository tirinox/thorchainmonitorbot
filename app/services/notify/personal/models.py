from typing import NamedTuple


class NodeChangeType:
    VERSION_CHANGED = 'version_change'
    NEW_VERSION_DETECTED = 'new_version'
    SLASHING = 'slashing'
    CHURNED_IN = 'churned_in'
    CHURNED_OUT = 'churned_out'
    IP_ADDRESS_CHANGED = 'ip_address'
    # todo: add more types


class NodeChange(NamedTuple):
    address: str
    type: str
    data: object
    single_per_user: bool = False
