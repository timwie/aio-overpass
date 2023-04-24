"""Distance functions."""

from math import cos, hypot


def fast_distance(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """
    Distance between two coordinates using equirectangular approximation.

    This uses just one trig and one sqrt function, which makes it very fast.
    It is useful for small distances (up to a few km), but inaccurate for larger
    distances, depending on distance, bearing, and latitude.

    Returns:
        approximate distance in meters between the two coordinates

    References:
        - https://stackoverflow.com/a/53712712
        - https://www.movable-type.co.uk/scripts/latlong.html
        - https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html
    """
    # Equatorial radius R = 6_378_137m
    # 2*pi*R / 360 = 111319.49079327358m
    # 0.5 * pi/180 = 0.008726646259971648

    x = b_lat - a_lat
    y = (b_lon - a_lon) * cos((b_lat + a_lat) * 0.008726646)
    return 111_319.490793 * hypot(x, y)
