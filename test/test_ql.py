from aio_overpass.ql import one_of_filter, poly_clause

import pytest
from shapely import Polygon


@pytest.mark.xdist_group(name="fast")
def test_poly_filter():
    # same shape, just making sure either repeating the first coord or not is fine
    shape1 = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]])
    shape2 = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    actual1 = poly_clause(shape1)
    actual2 = poly_clause(shape2)
    expected = f'(poly:"0.0 0.0 1.0 0.0 1.0 1.0 0.0 1.0")'
    assert actual1 == actual2 == expected


@pytest.mark.xdist_group(name="fast")
def test_one_of_filter():
    actual = one_of_filter("key")
    expected = ""
    assert actual == expected

    actual = one_of_filter("key", "value1")
    expected = '[key="value1"]'
    assert actual == expected

    actual = one_of_filter("key", "value1", "value2")
    expected = '[key~"^value1$|^value2$"]'
    assert actual == expected

    actual = one_of_filter("key", "value1", "value2", "value3")
    expected = '[key~"^value1$|^value2$|^value3$"]'
    assert actual == expected
