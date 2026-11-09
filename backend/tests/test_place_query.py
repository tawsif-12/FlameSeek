import pytest
from place_query import location_query


@pytest.mark.parametrize(('query', 'expected'), [
    ('Show me fires in Bangladesh', 'Bangladesh'),
    ('Find historical fire activity in Dhaka last month', 'Dhaka'),
    ('wildfires near Los Angeles today', 'Los Angeles'),
    ('Sundarbans forest', 'Sundarbans forest'),
    ('Fire Island', 'Fire Island'),
    ('বাংলাদেশ', 'বাংলাদেশ'),
    ('Show me fires in', 'fires in'),
])
def test_location_query(query, expected):
    assert location_query(query) == expected
