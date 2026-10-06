"""HIDDEN grader — the sizes only exist in the Figma design.
The "Home Screen Widgets" COMPONENT_SET (node 775:13152) has variants
Size=Large / Size=Medium / Size=Small. Graded order-insensitively.
"""
from ios_widgets import home_screen_widget_sizes

def test_sizes_match_design():
    assert sorted(home_screen_widget_sizes()) == ["Large", "Medium", "Small"]
