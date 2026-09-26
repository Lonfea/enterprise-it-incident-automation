from src.feedback import noise_templates


def test_needs_enough_agreeing_verdicts():
    assert noise_templates([("t", False), ("t", False)]) == set()
    assert noise_templates([("t", False)] * 3) == {"t"}


def test_a_confirmed_incident_keeps_template_alerting():
    verdicts = [("t", False)] * 3 + [("t", True)]
    assert noise_templates(verdicts) == set()


def test_tolerance_is_configurable():
    verdicts = [("t", False)] * 10 + [("t", True)]
    assert noise_templates(verdicts) == set()
    assert noise_templates(verdicts, max_incident_rate=0.1) == {"t"}
