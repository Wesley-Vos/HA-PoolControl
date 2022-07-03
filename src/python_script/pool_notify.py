domain = data.get("domain", "")

pool_notifications = hass.states.get("input_boolean.pool_notifications").state == "on"

if not pool_notifications:
    exit(0)

def trigger(trig):
    if trig in ("online", "onlineSwim"):
        return "online"
    elif trig in ("button", "buttonSwim"):
        return "de knop"
    elif trig in ("watch", "watchSwim"):
        return "Watch"
    elif trig == "timer":
        return "de timer"
    elif trig == "heatpump":
        return "de verwarming"
    elif trig == "heated_timer":
        return "de verwarmde timer"
    elif trig == "schedule":
        return "het schema"
    elif trig == "solar":
        return "de zon"
    elif trig == "reset":
        return "automatische modus"

def get_schedule_round():
    now_dt = datetime.datetime.now()
    end_schedule = datetime.datetime.strptime(hass.states.get("input_datetime.pool_schedule_end").state, "%H:%M:%S").replace(day=now_dt.day, month=now_dt.month, year=now_dt.year)
    diff = (now_dt - end_schedule).total_seconds()
    if diff < 0:
        return 0
    elif diff < 60:
        return 1
    else:
        return 2

def state(state):
    return "aan" if state == "on" else "uit"

if domain == "Pump":
    old_state = data.get("old_state", "")
    new_state = data.get("new_state", "")
    old_trigger = data.get("old_trigger", "")
    new_trigger = data.get("new_trigger", "")
    
    send = False
    manual = ["onlineSwim", "buttonSwim", "watchSwim"]

    if old_state == new_state and old_trigger != new_trigger:
        # trigger change

        if old_trigger == "solar" and new_trigger == "schedule":
            round = get_schedule_round()
            if round == 0:
                message = "Pomp begint met de eerste pompronde"
            elif round == 1:
                message = "Pomp gaat verder met de eerste pompronde"
            elif round == 2:
                message = "Pomp gaat verder met de tweede pompronde"
        elif old_trigger == "schedule" and new_trigger == "solar":
            if get_schedule_round() == 1:
                message = "Eerste pompronde voltooid, gaat verder op de zon"
            else:
                message = "Dagelijks schema is voltooid, gaat verder op de zon"
        #elif old_trigger in manual and new_trigger == "schedule":
        #    if get_schedule_round() == 1:
        #        message = "Handmatig is gereset, gaat verder met eerste pompronde"
        #    else:
        #        message = "Handmatig is gereset, gaat verder met tweede pompronde"
        elif new_trigger == "schedule":
            round = get_schedule_round()
            if round == 0:
                end = str(hass.states.get("input_datetime.pool_schedule_end").state)[0:5]
                message = "Pomp is gewijzigd van " + trigger(old_trigger) + " naar schema en begint met de eerste pompronde met eindtijd " + end + "."
            elif round == 1:
                end = str(hass.states.get("input_datetime.pool_schedule_end").state)[0:5]
                message = "Pomp is gewijzigd van " + trigger(old_trigger) + " naar schema en gaat verder met de eerste pompronde met eindtijd " + end + "."
            elif round == 2:
                end = str(hass.states.get("input_datetime.pool_schedule_last_cycle_end").state)[0:5]
                message = "Pomp is gewijzigd van " + trigger(old_trigger) + " naar schema en gaat verder met de tweede pompronde met eindtijd " + end + "."
        else:
            message = "Pomp is gewijzigd van " + trigger(old_trigger) + " naar " + trigger(new_trigger) + ", blijft " + state(new_state)
        send = True
    elif old_state != new_state:
        # new state
        if new_state == "on":
            if new_trigger == "schedule":
                end = str(hass.states.get("input_datetime.pool_schedule_end").state)[0:5]
                round = get_schedule_round()
                if round == 0:
                    message = "Pomp begint met de eerste pompronde met eindtijd " + end
                elif round == 1:
                    message = "Pomp gaat verder met de eerste pompronde met eindtijd " + end
                elif round == 2:
                    end = str(hass.states.get("input_datetime.pool_schedule_last_cycle_end").state)[0:5]
                    message = "Pomp is ingeschakeld voor tweede pompronde met eindtijd " + end
            elif new_trigger == "solar":
                power = hass.states.get("sensor.util_power_solar_average").state
                message = "Pomp is ingeschakeld door de zon (" + power + "W)"
            elif new_trigger == "timer":
                end = str(hass.states.get("input_datetime.pool_timer_end").state)[10:16]
                message = "Pomp is ingeschakeld door de timer die eindigt om " + end + "."
            else:
                message = "Pomp is ingeschakeld door " + trigger(new_trigger)
        elif new_state == "off":
            message = "Pomp is uitgeschakeld door " + trigger(new_trigger)
        send = True
    else:
        # do nothing
        send = False

    if send == True:
        data = {
            "title": "Pool",
            "message": message
        }
        hass.services.call("notify", "mobile_app_iphone_van_wesley", service_data=data)        


