from xrepotest.crawler.models import (
    ArgumentDefinition,
    FunctionComponent,
    FunctionMetadata,
)


def test_argument_definition_defaults():
    arg = ArgumentDefinition(name="limit")

    assert arg.name == "limit"
    assert arg.type is None
    assert arg.default is None
    assert arg.position == 0


def test_function_component_holds_fields():
    component = FunctionComponent(
        name="compute",
        signature="compute(x, y)",
        start_line=10,
        end_line=25,
    )

    assert component.name == "compute"
    assert component.signature == "compute(x, y)"
    assert component.start_line == 10
    assert component.end_line == 25


def test_function_metadata_composition():
    component = FunctionComponent(
        name="sum_values",
        signature="sum_values(a, b)",
        start_line=1,
        end_line=4,
    )
    metadata = FunctionMetadata(
        function_name="sum_values",
        file_path="src/math.go",
        focal_code="func sum_values(a, b int) int { return a + b }",
        file_content="package math\nfunc sum_values(a, b int) int { return a + b }",
        language="go",
        function_component=component,
        metadata={"package": "math"},
    )

    assert metadata.function_name == "sum_values"
    assert metadata.file_path == "src/math.go"
    assert metadata.language == "go"
    assert metadata.function_component == component
    assert metadata.metadata == {"package": "math"}
