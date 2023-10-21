from test.integration._element import validate_elements_in_result_set


assert __name__ == "__main__"

validate_elements_in_result_set(
    code="""
[timeout:60];
area[name="Barmbek-Nord"][boundary=administrative];
nwr(area);
out geom;
"""
)
