from test.integration._element import validate_elements_in_result_set


assert __name__ == "__main__"

validate_elements_in_result_set(
    code="""
[timeout:60];
area[wikipedia="en:City of London"];
nwr(area);
out geom;
"""
)
