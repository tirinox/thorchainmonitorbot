import re
from typing import NamedTuple, Dict, Any, Tuple

_AS_PATTERN = re.compile(r'^\s*AS(\d+)\s*(.*)$', re.IGNORECASE)


def parse_as(text) -> Tuple[int, str]:
    """ "AS14061 DigitalOcean, LLC" => (14061, "DigitalOcean, LLC"); (0, "") if there is no AS number """
    m = _AS_PATTERN.match(str(text or ''))
    return (int(m.group(1)), m.group(2).strip()) if m else (0, '')


class LocationInfo(NamedTuple):
    ip: str
    org: str = ''
    latitude: float = 0
    longitude: float = 0
    country_name: str = ''
    country_code: str = ''
    city: str = ''
    # new fields go last: a node list saved to the DB keeps this tuple as a plain list
    asn: int = 0  # the number of the autonomous system, 0 if unknown
    as_name: str = ''
    isp: str = ''

    @property
    def has_location(self) -> bool:
        return bool(self.latitude or self.longitude)

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "LocationInfo":
        asn, _ = parse_as(data.get("asn", ""))
        return cls(
            ip=data.get("ip", ""),
            org=data.get("org", ""),
            latitude=float(data.get("latitude", 0.0)),
            longitude=float(data.get("longitude", 0.0)),
            country_name=data.get("country_name", ""),
            country_code=data.get("country_code", ""),
            city=data.get("city", ""),
            asn=asn,
            as_name=data.get("org", ""),
        )

    @classmethod
    def from_alt_json(cls, data: Dict[str, Any]) -> "LocationInfo":
        """Parse JSON in the second provider's format"""
        asn, as_name = parse_as(data.get("as", ""))
        isp = data.get("isp") or ""
        return cls(
            ip=data.get("query", ""),
            org=data.get("org") or isp,  # the org is often an empty string
            latitude=float(data.get("lat", 0.0)),
            longitude=float(data.get("lon", 0.0)),
            country_name=data.get("country", ""),
            country_code=data.get("countryCode", ""),
            city=data.get("city", ""),
            asn=asn,
            as_name=as_name,
            isp=isp,
        )
