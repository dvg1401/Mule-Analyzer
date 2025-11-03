import json
from pathlib import Path


from mule_analyzer.cli import main as cli_main
from tests.test_parser_basic import SAMPLE_XML


def test_cli_generates_json(tmp_path, capsys):
    xml_path = tmp_path / "example.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    output_path = tmp_path / "result.json"

    exit_code = cli_main([str(xml_path), "--project", "CliProject", "--out", str(output_path), "--pretty"])

    assert exit_code == 0
    assert output_path.exists()

    captured = capsys.readouterr()
    assert str(output_path) in captured.out

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["project"] == "CliProject"
    assert data["flows"]


def test_cli_default_output_name(tmp_path, capsys):
    xml_path = tmp_path / "router.mule.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")

    exit_code = cli_main([str(xml_path), "--project", "DefaultNameProject"])

    assert exit_code == 0

    captured = capsys.readouterr()
    output_line = captured.out.strip().splitlines()[-1]
    generated_path = output_line.rsplit(" ", 1)[-1]
    json_path = Path(generated_path)

    assert json_path.exists()
    assert json_path.name == "router.mule.json"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["project"] == "DefaultNameProject"
