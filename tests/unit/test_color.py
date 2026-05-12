import App


def test_default_constructor_zero_initialized():
    c = App.TGColorA()
    assert c.GetR() == 0.0
    assert c.GetG() == 0.0
    assert c.GetB() == 0.0
    assert c.GetA() == 0.0


def test_set_rgba_populates_components():
    c = App.TGColorA()
    c.SetRGBA(0.25, 0.5, 0.75, 1.0)
    assert c.GetR() == 0.25
    assert c.GetG() == 0.5
    assert c.GetB() == 0.75
    assert c.GetA() == 1.0


def test_individual_setters():
    c = App.TGColorA()
    c.SetR(0.1); c.SetG(0.2); c.SetB(0.3); c.SetA(0.4)
    assert (c.GetR(), c.GetG(), c.GetB(), c.GetA()) == (0.1, 0.2, 0.3, 0.4)


def test_attribute_access_reads_and_writes():
    # UITree.py and StylizedWindow.py use kColor.r / kColor.r = 0.0
    c = App.TGColorA()
    c.r = 0.9; c.g = 0.8; c.b = 0.7; c.a = 0.6
    assert c.r == 0.9 and c.g == 0.8 and c.b == 0.7 and c.a == 0.6
    # method readback agrees with attribute write
    assert c.GetR() == 0.9


def test_scale_rgb_scales_only_rgb_not_alpha():
    c = App.TGColorA()
    c.SetRGBA(0.1, 0.2, 0.4, 0.5)
    c.ScaleRGB(2.0)
    assert c.GetR() == 0.2
    assert c.GetG() == 0.4
    assert c.GetB() == 0.8
    assert c.GetA() == 0.5  # alpha untouched


def test_copy_copies_all_components():
    src = App.TGColorA()
    src.SetRGBA(0.11, 0.22, 0.33, 0.44)
    dst = App.TGColorA()
    dst.Copy(src)
    assert (dst.GetR(), dst.GetG(), dst.GetB(), dst.GetA()) == (0.11, 0.22, 0.33, 0.44)
    # mutating src does not affect dst
    src.SetR(0.99)
    assert dst.GetR() == 0.11


def test_hardpoint_usage_pattern_does_not_crash():
    # Mirrors sunbuster.py:103-104 and StylizedWindow.py:624-627
    glow = App.TGColorA()
    glow.SetRGBA(0.294118, 0.184314, 0.811765, 0.466667)
    assert glow.GetR() > 0.0
    box = App.TGColorA()
    box.r = 0.0; box.g = 0.0; box.b = 0.0; box.a = 0.9
    assert box.a == 0.9
