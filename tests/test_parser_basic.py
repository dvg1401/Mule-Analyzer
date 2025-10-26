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


