from mule_analyzer import parse_mule_xml


SAMPLE_XML = """
<mule xmlns="http://www.mulesoft.org/schema/mule/core"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xmlns:http="http://www.mulesoft.org/schema/mule/http"
      xmlns:ee="http://www.mulesoft.org/schema/mule/ee/core"
      xmlns:doc="http://www.mulesoft.org/schema/mule/documentation">
  <flow name="mainFlow">
    <http:listener config-ref="httpListenerConfig" path="/api" methods="GET" doc:name="HTTP Listener"/>
    <ee:transform doc:name="Transform">
      <ee:message>
        <ee:set-payload><![CDATA[%dw 2.0
output application/json
---
{
  message: "hello"
}
]]></ee:set-payload>
      </ee:message>
    </ee:transform>
    <flow-ref name="helperSubflow" doc:name="Call subflow"/>
    <error-handler>
      <on-error-propagate when="error.description == 'boom'" statusCode="500">
        <flow-ref name="helperSubflow" doc:name="Error handler call"/>
        <set-payload value="Error"/>
      </on-error-propagate>
    </error-handler>
  </flow>
  <sub-flow name="helperSubflow">
    <logger level="INFO" message="Helper" doc:name="Logger"/>
  </sub-flow>
</mule>
""".strip()


ROUTER_XML = """
<mule xmlns="http://www.mulesoft.org/schema/mule/core"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xmlns:doc="http://www.mulesoft.org/schema/mule/documentation">
  <flow name="routerFlow">
    <choice doc:name="Choice">
      <when expression="#[vars.flag]">
        <flow-ref name="flagged" doc:name="Flagged"/>
      </when>
      <otherwise>
        <flow-ref name="fallback" doc:name="Fallback"/>
      </otherwise>
    </choice>
    <scatter-gather doc:name="Scatter">
      <route>
        <flow-ref name="routeOne" doc:name="Route1"/>
      </route>
      <route>
        <flow-ref name="routeTwo" doc:name="Route2"/>
      </route>
    </scatter-gather>
    <first-successful doc:name="First">
      <route>
        <flow-ref name="firstOption" doc:name="First option"/>
      </route>
    </first-successful>
    <foreach doc:name="Loop">
      <flow-ref name="loopSub" doc:name="Loop sub"/>
    </foreach>
  </flow>
  <sub-flow name="flagged"/>
  <sub-flow name="fallback"/>
  <sub-flow name="routeOne"/>
  <sub-flow name="routeTwo"/>
  <sub-flow name="firstOption"/>
  <sub-flow name="loopSub"/>
</mule>
""".strip()


def test_basic_flow_structure():
    result = parse_mule_xml(SAMPLE_XML, project="DemoProject")

    assert result["schemaVersion"] == "1.0.0"
    assert result["project"] == "DemoProject"
    assert result["flows"]
    flow = result["flows"][0]
    assert flow["id"] == "flow://mainFlow"
    assert flow["processors"][0]["type"] == "http:listener"
    assert flow["processors"][0]["configRef"] == "httpListenerConfig"
    assert flow["processors"][0]["attributes"]["path"] == "/api"

    transform = flow["processors"][1]
    assert transform["type"] == "ee:transform"
    assert "dw" in transform
    assert transform["dw"]["version"] == "2.0"

    edges = flow["edges"]
    assert edges == [{"to": "subflow://helperSubflow", "via": "flow-ref"}]

    subflows = result["subflows"]
    assert subflows[0]["id"] == "subflow://helperSubflow"
    assert subflows[0]["processors"][0]["type"] == "logger"


def test_error_handler_parsing():
    result = parse_mule_xml(SAMPLE_XML, project="DemoProject")
    flow = result["flows"][0]
    error_handler = flow["errorHandler"]
    assert error_handler["onError"][0]["type"] == "on-error-propagate"
    assert error_handler["onError"][0]["when"] == "error.description == 'boom'"
    assert error_handler["onError"][0]["target"] == "subflow://helperSubflow"


def test_router_branches_and_edges():
    result = parse_mule_xml(ROUTER_XML, project="RouterProject")
    flow = next(flow for flow in result["flows"] if flow["name"] == "routerFlow")

    choice = flow["processors"][0]
    assert choice["type"] == "choice"
    assert choice["branches"][0]["when"] == "#[vars.flag]"
    assert choice["branches"][0]["targets"] == ["subflow://flagged"]
    assert choice["branches"][1]["otherwise"] is True
    assert choice["branches"][1]["targets"] == ["subflow://fallback"]

    scatter = flow["processors"][1]
    assert scatter["type"] == "scatter-gather"
    scatter_targets = [branch["targets"] for branch in scatter["branches"]]
    assert scatter_targets == [["subflow://routeOne"], ["subflow://routeTwo"]]

    first_successful = flow["processors"][2]
    assert first_successful["type"] == "first-successful"
    assert first_successful["branches"][0]["targets"] == ["subflow://firstOption"]

    foreach = flow["processors"][3]
    assert foreach["type"] == "foreach"
    assert foreach["branches"][0]["targets"] == ["subflow://loopSub"]

    via_counts = {
        "choice.when": 0,
        "choice.otherwise": 0,
        "scatter-gather": 0,
        "first-successful": 0,
        "foreach": 0,
    }
    for edge in flow["edges"]:
        if edge["via"] in via_counts:
            via_counts[edge["via"]] += 1

    assert via_counts == {
        "choice.when": 1,
        "choice.otherwise": 1,
        "scatter-gather": 2,
        "first-successful": 1,
        "foreach": 1,
    }


