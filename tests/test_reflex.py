from teela_core.reflex.reflex_layer import ReflexLayer, SensorReading, ReflexCommand


def test_reflex_halt_on_close_obstacle():
    reflex = ReflexLayer()
    readings = [
        SensorReading("ultrasonic_front", 0.3),
        SensorReading("ultrasonic_left", 2.0),
    ]
    cmd = reflex.evaluate(readings)
    assert cmd.cmd in ("HALT", "EMERGENCY_PARK")


def test_reflex_nominal_clear_path():
    reflex = ReflexLayer()
    readings = [
        SensorReading("ultrasonic_front", 2.0),
        SensorReading("ultrasonic_left", 2.0),
    ]
    cmd = reflex.evaluate(readings)
    assert cmd.cmd == "RESUME"


def test_reflex_emergency_after_two_breaches():
    reflex = ReflexLayer()
    readings = [SensorReading("ultrasonic_front", 0.3)]
    cmd1 = reflex.evaluate(readings)
    assert cmd1.cmd == "HALT"
    cmd2 = reflex.evaluate(readings)
    assert cmd2.cmd == "EMERGENCY_PARK"
