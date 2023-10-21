from test.integration._route import validate_routes_in_result_set


assert __name__ == "__main__"

validate_routes_in_result_set(
    code="""
[timeout:180];
area[name="Barmbek-Nord"][boundary=administrative];
rel(area)[type=route]->.routes;
"""
)
