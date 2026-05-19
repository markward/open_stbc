"""Unit tests for engine.appc.ai.iter_ais_with_external_function.

Walks an AI subtree (Plain / PriorityList / Sequence / Conditional /
Preprocessing / Builder) and yields PlainAI instances whose
RegisterExternalFunction map contains the requested function name."""
from engine.appc.ai import (
    PlainAI_Create, PriorityListAI_Create, SequenceAI_Create,
    ConditionalAI_Create, PreprocessingAI_Create,
    iter_ais_with_external_function,
)
from engine.appc.ships import ShipClass


def _make_leaf(ship, name, register_set_target=True):
    leaf = PlainAI_Create(ship, name)
    if register_set_target:
        leaf.RegisterExternalFunction(
            "SetTarget", {"FunctionName": f"SetTargetOn_{name}"})
    return leaf


def test_single_leaf_with_registered_function_is_yielded():
    ship = ShipClass()
    leaf = _make_leaf(ship, "Leaf")
    result = list(iter_ais_with_external_function(leaf, "SetTarget"))
    assert result == [leaf]


def test_single_leaf_without_function_yields_nothing():
    ship = ShipClass()
    leaf = _make_leaf(ship, "Leaf", register_set_target=False)
    assert list(iter_ais_with_external_function(leaf, "SetTarget")) == []


def test_priority_list_walks_all_children():
    ship = ShipClass()
    a = _make_leaf(ship, "A")
    b = _make_leaf(ship, "B")
    p = PriorityListAI_Create(ship, "P")
    p.AddAI(a, priority=1); p.AddAI(b, priority=2)
    result = list(iter_ais_with_external_function(p, "SetTarget"))
    assert set(result) == {a, b}


def test_sequence_walks_all_children():
    ship = ShipClass()
    a = _make_leaf(ship, "A")
    b = _make_leaf(ship, "B")
    s = SequenceAI_Create(ship, "S")
    s.AddAI(a); s.AddAI(b)
    assert set(iter_ais_with_external_function(s, "SetTarget")) == {a, b}


def test_conditional_walks_contained():
    ship = ShipClass()
    inner = _make_leaf(ship, "Inner")
    c = ConditionalAI_Create(ship, "C")
    c.SetContainedAI(inner)
    assert list(iter_ais_with_external_function(c, "SetTarget")) == [inner]


def test_preprocessing_walks_contained():
    ship = ShipClass()
    inner = _make_leaf(ship, "Inner")
    pp = PreprocessingAI_Create(ship, "PP")
    pp.SetContainedAI(inner)
    assert list(iter_ais_with_external_function(pp, "SetTarget")) == [inner]


def test_nested_composites_are_walked_recursively():
    """Sequence containing a PriorityList containing leaves — all
    matching leaves come out regardless of depth."""
    ship = ShipClass()
    a = _make_leaf(ship, "A")
    b = _make_leaf(ship, "B")
    p = PriorityListAI_Create(ship, "P")
    p.AddAI(a, priority=1); p.AddAI(b, priority=2)
    s = SequenceAI_Create(ship, "S")
    s.AddAI(p)
    assert set(iter_ais_with_external_function(s, "SetTarget")) == {a, b}


def test_unregistered_function_name_yields_nothing():
    ship = ShipClass()
    leaf = _make_leaf(ship, "Leaf")
    # Leaf registered "SetTarget"; we ask for a different name.
    assert list(iter_ais_with_external_function(leaf, "Fire")) == []


def test_none_root_yields_nothing():
    """Defensive: None root returns empty iterator, no crash."""
    assert list(iter_ais_with_external_function(None, "SetTarget")) == []
