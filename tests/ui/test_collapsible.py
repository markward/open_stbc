from engine.ui import UiCollapsibleList, bindings


def test_collapsible_renders_header_with_title_and_arrow(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    root = bindings.panel_root(pid)
    coll = UiCollapsibleList(parent_element=root, label="Bird of Prey-1",
                             affiliation="enemy", expanded=True)
    # Header has two children: arrow region and title region.
    header_classes = fake_dom.element(coll.header_element_id).classes
    assert "bc-collapsible-header" in header_classes
    assert "aff-enemy" in header_classes
    arrow_id, title_id = fake_dom.children(coll.header_element_id)
    assert "bc-arrow"  in fake_dom.element(arrow_id).classes
    assert "bc-title"  in fake_dom.element(title_id).classes
    assert fake_dom.element(title_id).text == "Bird of Prey-1"


def test_collapsible_menu_level_class_when_no_affiliation(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    root = bindings.panel_root(pid)
    coll = UiCollapsibleList(parent_element=root, label="Subsystems",
                             menu_level=3)
    classes = fake_dom.element(coll.header_element_id).classes
    assert "menu-3" in classes
    assert not any(c.startswith("aff-") for c in classes)


def test_collapsible_set_label_updates_title_element(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="One", affiliation="friendly")
    coll.set_label("Two")
    title_id = fake_dom.children(coll.header_element_id)[1]
    assert fake_dom.element(title_id).text == "Two"


def test_collapsible_destroy_removes_subtree(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    root = bindings.panel_root(pid)
    coll = UiCollapsibleList(parent_element=root, label="X",
                             affiliation="neutral")
    assert fake_dom.children(root) != []
    coll.destroy()
    assert fake_dom.children(root) == []


def test_collapsible_starts_expanded_by_default(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy")
    # The children container is the second wrapper child
    wrapper = fake_dom.children(bindings.panel_root(pid))[0]
    children_container = fake_dom.children(wrapper)[1]
    assert fake_dom.element(children_container).visible is True


def test_collapsible_starts_collapsed_when_requested(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy", expanded=False)
    wrapper = fake_dom.children(bindings.panel_root(pid))[0]
    children_container = fake_dom.children(wrapper)[1]
    assert fake_dom.element(children_container).visible is False


def test_arrow_click_toggles_expansion(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy")
    arrow_id = fake_dom.children(coll.header_element_id)[0]
    assert coll.expanded
    fake_dom.fire_click(arrow_id)
    assert not coll.expanded
    fake_dom.fire_click(arrow_id)
    assert coll.expanded


def test_header_class_reflects_expanded_state(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy")
    assert "expanded" in fake_dom.element(coll.header_element_id).classes
    coll.set_expanded(False)
    assert "collapsed" in fake_dom.element(coll.header_element_id).classes
    assert "expanded" not in fake_dom.element(coll.header_element_id).classes


def test_title_click_does_not_toggle_expansion(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy")
    title_id = fake_dom.children(coll.header_element_id)[1]
    fake_dom.fire_click(title_id)
    assert coll.expanded  # unchanged


def test_title_click_fires_on_click_callback(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    fired: list[str] = []
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy",
                             on_click=lambda: fired.append("hit"))
    title_id = fake_dom.children(coll.header_element_id)[1]
    fake_dom.fire_click(title_id)
    assert fired == ["hit"]


def test_arrow_click_does_not_fire_on_click(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    fired: list[str] = []
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy",
                             on_click=lambda: fired.append("nope"))
    arrow_id = fake_dom.children(coll.header_element_id)[0]
    fake_dom.fire_click(arrow_id)
    assert fired == []


def test_set_selected_updates_header_class(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    coll = UiCollapsibleList(parent_element=bindings.panel_root(pid),
                             label="x", affiliation="enemy")
    assert "selected" not in fake_dom.element(coll.header_element_id).classes
    coll.set_selected(True)
    assert "selected" in fake_dom.element(coll.header_element_id).classes
