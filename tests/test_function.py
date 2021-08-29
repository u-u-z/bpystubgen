from inspect import cleandoc

from docutils.frontend import OptionParser
from docutils.nodes import document
from docutils.parsers.rst import Parser
from docutils.utils import new_document
from pytest import fixture, mark

from bpystubgen.nodes import Argument, Class, Function, FunctionScope, Module


@fixture
def parser() -> Parser:
    return Parser()


@fixture
def document() -> document:
    components = (Parser,)
    settings = OptionParser(components=components).get_default_values()

    return new_document("", settings=settings)


# noinspection DuplicatedCode
def test_parse_simple(parser: Parser, document: document):
    source = cleandoc("""
        .. function:: loadGlobalDict()

           Loads :class:`~bge.logic.globalDict` from a file.
    """)

    parser.parse(source, document)
    document.transformer.apply_transforms()

    assert len(document.children) == 1

    func = document.children[0]

    assert isinstance(func, Function)

    assert func.name == "loadGlobalDict"
    assert not func.type
    assert func.docstring and func.docstring.astext() == \
           "Loads :class:`globalDict <bge.logic.globalDict>` from a file."


@mark.parametrize("signature", (
        ".. function:: glBlendFunc(sfactor, dfactor)  ",
        ".. function::   glBlendFunc(sfactor, dfactor)",
        ".. function:: glBlendFunc(sfactor, dfactor):",
        ".. function:: glBlendFunc  (sfactor, dfactor) : "))
def test_parse_with_spaces(parser: Parser, document: document, signature: str):
    parser.parse(signature, document)
    document.transformer.apply_transforms()

    assert len(document.children) == 1

    func = document.children[0]

    assert isinstance(func, Function)

    assert func.name == "glBlendFunc"
    assert not func.type

    assert len(func.arguments) == 2
    assert func.arguments[0].name == "sfactor"
    assert func.arguments[1].name == "dfactor"


# noinspection DuplicatedCode
def test_parse_with_rtype(parser: Parser, document: document):
    source = cleandoc("""
        .. function:: LibList()

           Returns a list of currently loaded libraries.

           :rtype: list [str]
    """)

    parser.parse(source, document)
    document.transformer.apply_transforms()

    assert len(document.children) == 1

    func = document.children[0]

    assert isinstance(func, Function)

    assert func.name == "LibList"
    assert func.type == "typing.List[str]"


def test_parse_with_args(parser: Parser, document: document):
    source = cleandoc("""
    .. function:: LibNew(name, type, data)

       Uses existing datablock data and loads in as a new library.

       :arg name: A unique library name used for removal later
       :type name: string
       :arg type: The datablock type (currently only "Mesh" is supported)
       :type type: string
       :arg data: A list of names of the datablocks to load
       :type data: list of strings
    """)

    parser.parse(source, document)
    document.transformer.apply_transforms()

    assert len(document.children) == 1

    func = document.children[0]

    assert isinstance(func, Function)

    assert func.name == "LibNew"
    assert not func.type
    assert func.docstring and func.docstring.children[0].astext() == \
           "Uses existing datablock data and loads in as a new library."

    args = func.arguments

    assert len(args) == 3

    assert args[0].name == "name"
    assert args[0].type == "str"

    assert args[1].name == "type"
    assert args[1].type == "str"

    assert args[2].name == "data"
    assert args[2].type == "typing.List[str]"


@mark.parametrize("default", [
    "None",
    "'value'",
    "\"value\"",
    "image.filepath",
    "list()",
    "[(1, 2, 3)]"])
def test_arg_default_value(parser: Parser, document: document, default):
    source = f".. function:: init(name, value = {default})"

    parser.parse(source, document)
    document.transformer.apply_transforms()

    func = document.children[0]

    assert isinstance(func, Function)

    args = func.arguments

    assert len(args) == 2

    assert args[1].name == "value"
    assert args[1].default == default


def test_parse_overloading(parser: Parser, document: document):
    source = cleandoc("""
       .. staticmethod:: chain(it, pred, modifier)
                         chain(it, pred)

          :arg it: The iterator on the ViewEdges of the ViewMap. It contains
             the chaining rule.
          :type it: :class:`ViewEdgeIterator`
          :arg pred: The predicate on the ViewEdge that expresses the
             stopping condition.
          :type pred: :class:`UnaryPredicate1D`
          :arg modifier: A function that takes a ViewEdge as argument and
             that is used to modify the processed ViewEdge state (the
             timestamp incrementation is a typical illustration of such a modifier).
             If this argument is not given, the time stamp is automatically managed.
          :type modifier: :class:`UnaryFunction1DVoid`
    """)

    parser.parse(source, document)
    document.transformer.apply_transforms()

    assert len(document.children) == 2

    (func1, func2) = document.children

    assert isinstance(func1, Function)
    assert isinstance(func2, Function)

    assert func1.name == "chain"
    assert func2.name == "chain"

    assert not func1.type
    assert not func2.type

    assert len(func1.arguments) == 3
    assert len(func2.arguments) == 2

    assert tuple(map(lambda a: a.name, func1.arguments)) == ("it", "pred", "modifier")
    assert tuple(map(lambda a: a.name, func2.arguments)) == ("it", "pred")


def test_signature():
    func = Function(name="my_func")
    assert func.signature == "def my_func() -> None:"

    func.type = "str"
    assert func.signature == "def my_func() -> str:"

    func.scope = FunctionScope.Class
    assert func.signature == "@classmethod\ndef my_func(cls) -> str:"

    func.scope = FunctionScope.Instance
    assert func.signature == "def my_func(self) -> str:"

    func.scope = FunctionScope.Static
    assert func.signature == "@staticmethod\ndef my_func() -> str:"

    func.scope = FunctionScope.Module
    assert func.signature == "def my_func() -> str:"

    arg1 = Argument(name="arg1")
    func += arg1

    assert func.signature == "def my_func(arg1: typing.Any) -> str:"

    arg1.type = "int"

    arg2 = Argument(name="arg2", type="str", default="None")
    func += arg2

    assert func.signature == "def my_func(arg1: int, arg2: str = None) -> str:"


def test_type_resolution():
    func = Function(name="my_func")
    func.type = "mymodule.LocalClass1"

    func += Argument(name="arg1", type="mymodule.LocalClass2")
    func += Argument(name="arg2", type="other.ExternalClass")

    module = Module(name="mymodule")

    module += Class(name="LocalClass1")
    module += Class(name="LocalClass2")

    module += func

    assert func.signature == \
           "def my_func(arg1: LocalClass2, arg2: other.ExternalClass) -> LocalClass1:"
