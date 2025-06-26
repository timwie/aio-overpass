import json
from pathlib import Path

from aio_overpass import Query
from aio_overpass.element import collect_elements


def test_geos_topology_exception_handling():
    test_dir = Path(__file__).resolve().parent
    data_file = test_dir / "element_data" / "invalid_building_geometry.json"

    with data_file.open(encoding="utf-8") as file:
        elem = json.load(file)

    query = Query("")
    query._response = {"elements": [elem]}

    (elem_typed,) = collect_elements(query)
    assert (
        "TopologyException: side location conflict"
        in elem_typed.base_geometry_details.invalid_reason
    )
    assert elem_typed.base_geometry_details.valid is None
    assert elem_typed.base_geometry_details.accepted is None
    assert elem_typed.base_geometry_details.fixed is None
    assert elem_typed.base_geometry_details.invalid is not None
