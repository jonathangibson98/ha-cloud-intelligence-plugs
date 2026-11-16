from unittest.mock import patch
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from custom_components.cloud_intelligence_plugs.const import DOMAIN

INPUT={"name":"Galaxy Lights","device_name":"A1B2C3D4E5F6","access_key":"AbCdEfGh10x1Y",
       "access_token":"tok","host":"","product_key":"a1JG8An8ORa"}
P="custom_components.cloud_intelligence_plugs"

async def test_flow_and_switch(hass: HomeAssistant):
    state={"on":True}
    with patch(f"{P}.config_flow.discover",return_value={"a1b2c3d4e5f6":"192.168.1.50"}), \
         patch(f"{P}.alcs.AlcsPlug.test",return_value=True), \
         patch(f"{P}.alcs.AlcsPlug.get_power",side_effect=lambda: state["on"]), \
         patch(f"{P}.alcs.AlcsPlug.set_power",side_effect=lambda on: state.update(on=on)):
        r=await hass.config_entries.flow.async_init(DOMAIN,context={"source":config_entries.SOURCE_USER})
        assert r["type"] is FlowResultType.FORM
        r=await hass.config_entries.flow.async_configure(r["flow_id"],dict(INPUT))
        assert r["type"] is FlowResultType.CREATE_ENTRY, r
        assert r["data"]["host"]=="192.168.1.50" and r["data"]["device_name"]=="a1b2c3d4e5f6"
        await hass.async_block_till_done()
        st=hass.states.get("switch.galaxy_lights"); assert st and st.state=="on", st
        await hass.services.async_call("switch","turn_off",{"entity_id":"switch.galaxy_lights"},blocking=True)
        assert state["on"] is False and hass.states.get("switch.galaxy_lights").state=="off"
        # duplicate aborts
        r=await hass.config_entries.flow.async_init(DOMAIN,context={"source":config_entries.SOURCE_USER})
        r=await hass.config_entries.flow.async_configure(r["flow_id"],dict(INPUT))
        assert r["type"] is FlowResultType.ABORT
        # options change reloads with new interval
        e=hass.config_entries.async_entries(DOMAIN)[0]
        r=await hass.config_entries.options.async_init(e.entry_id)
        r=await hass.config_entries.options.async_configure(r["flow_id"],{"scan_interval":30})
        await hass.async_block_till_done()
        assert e.runtime_data.update_interval.total_seconds()==30
        assert await hass.config_entries.async_unload(e.entry_id)
