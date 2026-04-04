import math
import warnings


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    DEPRECATED: Calculate distance in kilometers between two points.
    All spatial routing and radius math has been offloaded to PostGIS ST_DWithin and ST_Distance math.
    """
    warnings.warn(
        "haversine is deprecated in favor of PostGIS ST_DWithin and ST_GeomFromText",
        DeprecationWarning,
        stacklevel=2,
    )
    r_earth = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return r_earth * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
