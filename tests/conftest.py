import ast
import importlib.abc
import importlib.machinery
import sys
import types
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SDK_SCRIPTS = PROJECT_ROOT / "sdk" / "Build" / "scripts"


class _MoveGlobalsToTop(ast.NodeTransformer):
    """Move global declarations to the top of each function body.

    SDK scripts were written for Python 1.5/2.x, which allowed using a name
    before its global declaration in the same function. Python 3 treats this
    as a SyntaxError at compile time.
    """
    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        globals_stmts = [s for s in node.body if isinstance(s, ast.Global)]
        other_stmts = [s for s in node.body if not isinstance(s, ast.Global)]
        node.body = globals_stmts + other_stmts
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


class _FixDottedImport(ast.NodeTransformer):
    """Rewrite bare __import__(x) → importlib.import_module(x).

    Python 1.5 returned the leaf module for a dotted __import__; Python 3
    returns the root. SDK scripts depend on the 1.5 behaviour for paths like
    "Systems.Biranu.Biranu1" in MissionLib.SetupSpaceSet and Systems.Utils.

    Only the single-argument no-keyword form is rewritten; __import__ calls
    with fromlist/level arguments are left unchanged.
    """
    def visit_Module(self, node):
        self.generic_visit(node)
        node.body.insert(0, ast.Import(
            names=[ast.alias(name="importlib", asname="_sdk_importlib")]
        ))
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
            and len(node.args) == 1
            and not node.keywords
        ):
            return ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="_sdk_importlib", ctx=ast.Load()),
                    attr="import_module",
                    ctx=ast.Load(),
                ),
                args=node.args,
                keywords=[],
            )
        return node


class _StubModule(types.ModuleType):
    """Module where any attribute access returns a no-op callable returning None.

    Used for SDK-side modules whose implementations are pure UI/bridge and
    irrelevant to Phase 1 headless logic.
    """
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _SDKLoader(importlib.abc.Loader):
    """Load an SDK script with Python 2 compatibility fixes applied."""

    def __init__(self, path: str):
        self.path = path

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        with open(self.path, encoding="utf-8", errors="replace") as f:
            source = f.read()
        source = source.expandtabs(4)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(source, filename=self.path)
        tree = _MoveGlobalsToTop().visit(tree)
        tree = _FixDottedImport().visit(tree)
        ast.fix_missing_locations(tree)
        code = compile(tree, self.path, "exec")
        exec(code, module.__dict__)


class _SDKFinder(importlib.abc.MetaPathFinder):
    """Find modules in sdk/Build/scripts/ and load them via _SDKLoader."""

    def find_spec(self, fullname, path, target=None):
        # Project root modules take priority — let normal finders handle them
        project_module = PROJECT_ROOT / (fullname.replace(".", "/") + ".py")
        if project_module.exists():
            return None
        candidate = SDK_SCRIPTS / (fullname.replace(".", "/") + ".py")
        if candidate.exists():
            loader = _SDKLoader(str(candidate))
            return importlib.machinery.ModuleSpec(
                fullname, loader, origin=str(candidate)
            )
        return None


def pytest_configure(config):
    # Our App.py must shadow sdk/Build/scripts/App.py
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # Install SDK finder before the default finders so SDK scripts get our
    # compatibility loader instead of the standard one.
    if not any(isinstance(f, _SDKFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _SDKFinder())

    # Callable stubs: attributes must be callable (return None).
    # loadspacehelper.CreateShip etc. are called by MissionLib; returning None
    # keeps the pPlayer != None guards false so creation branches are skipped.
    _callable_stubs = [
        "loadspacehelper",
        "LoadBridge",
    ]
    for name in _callable_stubs:
        if name not in sys.modules:
            sys.modules[name] = _StubModule(name)

    # Bridge.HelmMenuHandlers: callable stub that must also be accessible as an
    # attribute on the Bridge module (import Bridge.HelmMenuHandlers; then
    # Bridge.HelmMenuHandlers.attr = x). Pre-populate both sys.modules and the
    # parent module attribute so Python's import fast-path works without
    # requiring Bridge to have __path__.
    if "Bridge" not in sys.modules:
        sys.modules["Bridge"] = types.ModuleType("Bridge")
    if "Bridge.HelmMenuHandlers" not in sys.modules:
        _helm = _StubModule("Bridge.HelmMenuHandlers")
        sys.modules["Bridge.HelmMenuHandlers"] = _helm
        sys.modules["Bridge"].HelmMenuHandlers = _helm  # type: ignore[attr-defined]

    # Plain stubs: imported but no attributes accessed in Phase 1 code paths.
    _plain_stubs = [
        "Bridge.TacticalCharacterHandlers",
        "Bridge.HelmCharacterHandlers",
        "Bridge.XOCharacterHandlers",
        "Bridge.ScienceCharacterHandlers",
        "Bridge.EngineerCharacterHandlers",
        "BridgeHandlers",
        "Actions",
        "Actions.MissionScriptActions",
    ]
    for name in _plain_stubs:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
