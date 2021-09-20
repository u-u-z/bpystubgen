from __future__ import annotations

from pathlib import Path
from typing import AbstractSet, Iterable, MutableMapping, Optional, Sequence, ValuesView, cast

from docutils.core import publish_doctree
from docutils.frontend import Values
from docutils.io import FileInput, FileOutput
from docutils.nodes import document
from docutils.utils import new_document
from docutils.writers import Writer
from sphinx.environment import BuildEnvironment

from bpystubgen.nodes import Class, Import, Module


class Task:

    @classmethod
    def create(cls, src_dir: Path, pattern: str = "*.rst") -> Task:
        root = Task()

        def resolve(path: Sequence[str], context: Task) -> Task:
            count = len(path)

            assert count > 0

            name = path[0]

            if name in context.keys():
                child = context[name]
            elif name[0].islower():
                child = ModuleTask(name, parent=context)
            else:
                child = ClassTask(name, parent=context)

            if count == 1:
                return child

            return resolve(path[1:], child)

        for file in sorted(src_dir.rglob(pattern)):
            segments = file.name.split(".")[:-1]

            task = resolve(segments, root)
            task.source = file

        return root

    def __init__(self, name: str = "", parent: Optional[Task] = None) -> None:
        self._name = name
        self._parent = parent
        self._children: MutableMapping[str, Task] = dict()

        if parent:
            parent._children[self.name] = self

            segments = list(filter(any, map(lambda a: a.name, self.ancestors)))
            segments.append(self.name)

            self._full_name = ".".join(segments)
        else:
            self._full_name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_name(self) -> str:
        return self._full_name

    @property
    def parent(self) -> Optional[Task]:
        return self._parent

    @property
    def ancestors(self) -> Iterable[Task]:
        if self.parent:
            yield from self.parent.ancestors
            yield self.parent

    def keys(self) -> AbstractSet[str]:
        return self._children.keys()

    def values(self) -> ValuesView[Task]:
        return self._children.values()

    def __getitem__(self, key: str) -> Task:
        return self._children[key]

    def __iter__(self) -> Iterable[Task]:
        for child in self.values():
            yield from child.__iter__()
            yield child

    def __len__(self) -> int:
        return len(self._children)

    def __repr__(self) -> str:
        return self.full_name

    def __bool__(self) -> bool:
        return True


class ParserTask(Task):

    def __init__(self, name: str = "", parent: Optional[Task] = None) -> None:
        super().__init__(name, parent)

        self.source: Optional[Path] = None
        self.doctree: Optional[document] = None

    def parse(self, settings: Values, env: BuildEnvironment) -> Optional[document]:
        if self.source:
            source_path = str(self.source)

            env.project.docnames.add(source_path)
            env.prepare_settings(source_path)

            fin = FileInput(source_path=source_path)

            self.doctree = publish_doctree(
                fin,
                source_class=FileInput,
                source_path=source_path,
                settings=settings)

            fin.close()
        else:
            self.doctree = None

        return self.doctree


class ClassTask(ParserTask):
    pass


class ModuleTask(ParserTask):

    def parse(self, settings: Values, env: BuildEnvironment) -> Optional[document]:
        doctree = super().parse(settings, env)

        if not doctree:
            doctree = new_document("", settings=settings)
            doctree += Module(name=self.name)

        self.doctree = doctree

        module = next(iter(doctree.traverse(Module)))
        classes = filter(lambda c: isinstance(c, ClassTask), self.values())
        submodules = filter(lambda c: isinstance(c, ModuleTask), self.values())

        for child in classes:
            for node in cast(ClassTask, child).doctree.traverse(Class):
                node.parent.remove(node)
                module += node

        module.import_types()
        module.sort_members()

        index = 1 if module.docstring else 0

        for child in submodules:
            for node in cast(ModuleTask, child).doctree.traverse(Module):
                module.insert(index, Import(module=".", types=module.localise_name(node.name)))

        return doctree

    def target_path(self, dest_dir: Path) -> Path:
        top_level = not any(self.ancestors)
        has_submodule = any(filter(lambda c: isinstance(c, ModuleTask), self.values()))

        if top_level or has_submodule:
            parent_dir = Path(dest_dir, "/".join(self.full_name.split("."))).resolve()
            return parent_dir / "__init__.pyi"
        else:
            parent_dir = Path(dest_dir, "/".join(self.full_name.split(".")[:-1])).resolve()
            return parent_dir / (self.name + ".pyi")

    def generate(self, dest_dir: Path, writer: Writer) -> Optional[Path]:
        target = self.target_path(dest_dir)

        target.parent.mkdir(parents=True, exist_ok=True)

        marker = target.parent / "py.typed"

        with open(marker, "w"):
            pass

        fout = FileOutput(destination_path=str(target))

        writer.write(self.doctree, fout)
        writer.assemble_parts()

        fout.close()

        return target