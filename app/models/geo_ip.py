from typing import NamedTuple, Dict, Any


class LocationInfo(NamedTuple):
    ip: str
    org: str = ''
    latitude: float = 0
    longitude: float = 0
    country_name: str = ''
    country_code: str = ''
    city: str = ''

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "LocationInfo":
        return cls(
            ip=data.get("ip", ""),
            org=data.get("org", ""),
            latitude=float(data.get("latitude", 0.0)),
            longitude=float(data.get("longitude", 0.0)),
            country_name=data.get("country_name", ""),
            city=data.get("city", ""),
        )

    @classmethod
    def from_alt_json(cls, data: Dict[str, Any]) -> "LocationInfo":
        """Parse JSON in the second provider's format"""
        return cls(
            ip=data.get("query", ""),
            org=data.get("org", data.get("isp", "")),
            latitude=float(data.get("lat", 0.0)),
            longitude=float(data.get("lon", 0.0)),
            country_name=data.get("country", ""),
            country_code=data.get("countryCode", ""),
            city=data.get("city", ""),
        )
