"""Strict YAML loading for hand-edited configuration.

PyYAML silently keeps the last of duplicate keys (a second `approval:` would override the
first) and expands aliases; both are rejected here.
"""

from typing import Any

import yaml
from yaml.nodes import MappingNode, Node


class YamlStructureError(Exception):
    """Carries a stable code and a line number only, never document content."""

    def __init__(self, code: str, line: int | None) -> None:
        self.code = code
        self.line = line
        where = f" at line {line}" if line is not None else ""
        super().__init__(f"{code}{where}")


def _line(node_or_event: Any) -> int | None:
    mark = getattr(node_or_event, "start_mark", None)
    return mark.line + 1 if mark is not None else None


class StrictSafeLoader(yaml.SafeLoader):
    def compose_node(self, parent: Node | None, index: Any) -> Node | None:
        event = self.peek_event()  # type: ignore[no-untyped-call]
        if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None) is not None:
            raise YamlStructureError("yaml_alias_forbidden", _line(event))
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                # Merge keys are the alias mechanism of YAML 1.1 and can hide overrides.
                raise YamlStructureError("yaml_alias_forbidden", _line(key_node))
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in seen
            except TypeError as exc:
                raise YamlStructureError("yaml_invalid", _line(key_node)) from exc
            if duplicate:
                raise YamlStructureError("yaml_duplicate_key", _line(key_node))
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_strict(text: str) -> Any:
    """Load a single YAML document; raises `YamlStructureError` on any problem."""
    loader = StrictSafeLoader(text)
    try:
        return loader.get_single_data()
    except YamlStructureError:
        raise
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = mark.line + 1 if mark is not None else None
        raise YamlStructureError("yaml_invalid", line) from None
    except (yaml.YAMLError, RecursionError):
        raise YamlStructureError("yaml_invalid", None) from None
    finally:
        loader.dispose()
