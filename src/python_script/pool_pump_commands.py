command = data.get("command", "")
trigger = data.get("trigger", "")

def get_priority(trigger):
    priorities ={
        "online": 1, 
        "button": 1, 
        "watch": 1,
        "onlineSwim": 1, 
        "buttonSwim": 1, 
        "watchSwim": 1,
        "heated_timer": 2,
        "heatpump": 3,
        "after_timer": 4,
        "timer": 5,
        "schedule": 6,
        "solar": 7,
        "reset": 8
    }
    return priorities[trigger]

def pump(command, trigger, recover=False, after_timer=False):
    old_trigger = hass.states.get("input_select.pool_pump_trigger").state
    old_state = hass.states.get("switch.pool_pump_relay").state

    if command in ["on", "off"]:
        # trigger should have higher priority, otherwise send notification
        priority = get_priority(trigger)
        old_priority = float(hass.states.get("input_number.pool_pump_priority").state) 

        time_on = float(hass.states.get("sensor.pool_pump_time_on").state)*60
        max_time = float(hass.states.get("input_number.pool_pump_duration_upper_threshold").state)
        time_restricted = (time_on >= max_time) and trigger in ("schedule", "solar")
        
        if (priority <= old_priority or recover) and not time_restricted:
            # update trigger and priority
            hass.services.call("input_number", "set_value", service_data={"entity_id":"input_number.pool_pump_priority", "value": priority})
            hass.services.call("input_select", "select_option", service_data={"entity_id": "input_select.pool_pump_trigger", "option": trigger})
            
            # set current state of filter pump and notify
            hass.services.call("switch", "turn_" + command, {"entity_id": "switch.pool_pump_relay"})
            hass.services.call("python_script", "pool_notify", {"domain": "Pump", "old_state": old_state, "new_state": command , "old_trigger": old_trigger, "new_trigger": trigger })
            
            # set current state of heatpump (either set it on if heated_timer or heatpump is active, or if switched from heated_timer/heatpump towards priority 1)
            cmd_heatpump = "on" if command == "on" and trigger in ("heated_timer", "heatpump") or (priority == 1 and old_trigger in ("heated_timer", "heatpump")) else "off"
            hass.services.call("switch", "turn_" + cmd_heatpump, {"entity_id": "switch.pool_heatpump_climate"})
            
            # set after timer
            after_timer_planned = "on" if command == "on" and trigger in ("onlineSwim", "buttonSwim", "watchSwim", "heatpump", "heated_timer") else "off"
            after_timer_state = "on" if trigger == "after_timer" else "off"
            hass.services.call("input_boolean", "turn_" + after_timer_planned, {"entity_id": "input_boolean.pool_after_timer_planned"})
            hass.services.call("input_boolean", "turn_" + after_timer_state, {"entity_id": "input_boolean.pool_after_timer_active"})
        elif time_restricted:
            hass.services.call("input_number", "set_value", service_data={"entity_id":"input_number.pool_pump_priority", "value": 8})
            hass.services.call("input_select", "select_option", service_data={"entity_id": "input_select.pool_pump_trigger", "option": "reset"})
            hass.services.call("switch", "turn_off", {"entity_id": "switch.pool_pump_relay"})
            hass.services.call("switch", "turn_off", {"entity_id": "switch.pool_heatpump_climate"})
            data = {
                "title": "Pool",
                "message": "Pomp trigger " + trigger + "  genegeerd vanwege tijdslimiet, pomp gaat uit."
            }
            hass.services.call("notify", "mobile_app_iphone_van_wesley", service_data=data)
        elif command != old_state:
            data = {
                "title": "Pool",
                "message": "Pomp trigger " + trigger + " met lagere prioriteit genegeerd vanwege " + old_trigger + " wil je dit overbruggen?",
                "data":{"push": {"category": "PUMP_OVERRIDE"}}
            }
            hass.services.call("notify", "mobile_app_iphone_van_wesley", service_data=data)
        
    elif command == "recover":
        # check if pump has to be kept on or should but put off after ending a specific trigger
        priority = float(hass.states.get("input_number.pool_pump_priority").state)
        
        now = datetime.datetime.now()
        start_schedule = datetime.datetime.strptime(hass.states.get("input_datetime.pool_schedule_start").state, "%H:%M:%S").replace(day=now.day, month=now.month, year=now.year)
        start_last = datetime.datetime.strptime(hass.states.get("input_datetime.pool_schedule_last_cycle_start").state, "%H:%M:%S").replace(day=now.day, month=now.month, year=now.year)
        end_schedule = datetime.datetime.strptime(hass.states.get("input_datetime.pool_schedule_end").state, "%H:%M:%S").replace(day=now.day, month=now.month, year=now.year)
        remaining = int(hass.states.get("sensor.pool_pump_remaining_time").attributes['seconds'])
        
        # manual triggers
        if priority == 1.0 and trigger != "reset":
            # manually switched on, keep it
            pass
        elif hass.states.is_state("input_boolean.pool_timer_heat", "on") and hass.states.is_state("binary_sensor.pool_timer_active", "on"):
            # heated_timer is active
            hass.services.call("input_boolean", "turn_on", service_data={"entity_id": "input_boolean.pool_timer_state"})
            pump_call("on", "heated_timer", old_trigger)
        elif hass.states.is_state("switch.pool_heatpump_climate", "on") and old_trigger != "heated_timer": 
            # if old trigger was heated_timer and new one is not heated_timer (already skipped), then heatpump is switched off and will be set later on (in pump_call)
            # heatpump is on, pump has to be as well
            pump_call("on", "heatpump", old_trigger)
        elif hass.states.is_state("binary_sensor.pool_after_timer_active", "on") or after_timer:
            # after timer is active
            pump_call("on", "after_timer", old_trigger)
        elif hass.states.is_state("input_boolean.pool_after_timer_planned", "on"):
            # after timer is planned, calculate end time of pool_after_timer_end
            duration = float(hass.states.get("input_number.pool_after_timer_duration").state)
            end = (now + datetime.timedelta(minutes=duration))
            hass.services.call("input_datetime", "set_datetime", service_data = {"entity_id": "input_datetime.pool_after_timer_end", "datetime": "{}-{}-{} {}:{}:{}".format(end.year, ("0" if end.month < 10 else "") + str(end.month), ("0" if end.day < 10 else "") + str(end.day), end.hour, end.minute, end.second)})
            hass.services.call("input_boolean", "turn_off", {"entity_id": "input_boolean.pool_after_timer_planned"})
            hass.services.call("input_boolean", "turn_on", {"entity_id": "input_boolean.pool_after_timer_active"})
            pump("recover", "after_timer" if trigger != "reset" else "reset", after_timer=True)
        elif hass.states.is_state("binary_sensor.pool_timer_active", "on"):
            # timed schedule is active
            state = "on" if hass.states.is_state("input_boolean.pool_timer_state", "on") else "off"
            pump_call(state, "timer", old_trigger)
            
        # entering automatic triggers
        elif start_schedule <= now and now < end_schedule:
            # first round of schedule
            pump_call("on", "schedule", old_trigger)
        elif now >= start_last and remaining > 60:
            # second (optional) round of schedule
            pump_call("on", "schedule", old_trigger)
            end = (now + datetime.timedelta(seconds=remaining))
            hass.services.call("input_datetime", "set_datetime", service_data = {"entity_id": "input_datetime.pool_schedule_last_cycle_end", "time": "{}:{}:{}".format(end.hour, end.minute, end.second)})
        elif hass.states.is_state("binary_sensor.pool_solar_active", "on"):
        #elif float(hass.states.get("sensor.util_power_solar_average").state) >= float(hass.states.get("input_number.pool_solar_limit").state):
            # solar
            pump_call("on", "solar", old_trigger)
        else:
            # nothing should put the pump on, send put off command
            pump_call("off", "reset", old_trigger)
    else:
        logger.warning("Command not found")

def pump_call(command, trigger, old_trigger):
    time_on = float(hass.states.get("sensor.pool_pump_time_on").state)*60
    max_time = float(hass.states.get("input_number.pool_pump_duration_upper_threshold").state)
    time_restricted = (time_on >= max_time) and trigger in ("schedule", "solar")
    
    if time_restricted or old_trigger != trigger or command != hass.states.get("switch.pool_pump_relay").state:
        pump(command, trigger, recover=True)
        
pump(command, trigger)