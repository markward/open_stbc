from engine.ui import UiPanel, UiStatRow, bindings


def test_stat_row_renders_label_and_value(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    row = UiStatRow(parent_element=bindings.panel_root(pid),
                    label="Ship", value="Galaxy")
    el = fake_dom.element(row.element_id)
    assert "bc-stat-row" in el.classes
    label_id, value_id = fake_dom.children(row.element_id)
    assert "bc-stat-label" in fake_dom.element(label_id).classes
    assert "bc-stat-value" in fake_dom.element(value_id).classes
    assert fake_dom.element(label_id).text == "Ship"
    assert fake_dom.element(value_id).text == "Galaxy"


def test_stat_row_set_value_updates_dom(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    row = UiStatRow(parent_element=bindings.panel_root(pid),
                    label="Pos", value="0 0 0")
    row.set_value("1.5 2.5 3.5")
    value_id = fake_dom.children(row.element_id)[1]
    assert fake_dom.element(value_id).text == "1.5 2.5 3.5"


def test_stat_row_destroy_removes_from_dom(fake_dom):
    pid = bindings.create_panel("p", "top-right", 20.0, 60.0)
    root = bindings.panel_root(pid)
    row = UiStatRow(parent_element=root, label="X", value="Y")
    assert fake_dom.children(root) == [row.element_id]
    row.destroy()
    assert fake_dom.children(root) == []


def test_panel_stat_factory_attaches_row(fake_dom):
    panel = UiPanel(id="debug")
    row = panel.stat("Ship", "Galaxy")
    assert isinstance(row, UiStatRow)
    assert row.element_id in fake_dom.children(fake_dom.panel_root(panel.panel_id))
