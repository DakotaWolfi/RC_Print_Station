"""Cover the offline graph and its result semantics independently of the HMI."""
import unittest

from benning_guide import Guide, STEPS
from benning_output import electrical_check, measurement_summary, report_checks, result_kind, visible_measurements
from benning_workflow import fresh_slot


def path(*choices):
    g=Guide()
    for choice in choices:
        if not g.choose(choice):
            raise AssertionError((g.step,choice))
    return g


class GuideTests(unittest.TestCase):
    def test_standard_and_special_procedures_have_the_expected_mode_and_voltage(self):
        for route,procedure,mode,voltage,key in (
                ((0,0,0),"I","Netz",500,"Erdzeichen"),
                ((0,1,0),"II","Netz",500,"Doppelquadrat"),
                ((0,0,1,0),"I","Netz",250,"Erdzeichen"),
                ((0,1,1,1),"II","Batterie",500,"Doppelquadrat"),
                ((0,0,1,2),"I","Batterie",250,"Erdzeichen"),
                ((0,2,0,0),"III","Batterie",500,"Doppelquadrat"),
                ((0,2,0,1,0),"III","Batterie",250,"Doppelquadrat"),
                ((0,3,0,0),"IEC","Batterie",500,"Erdzeichen"),
                ((0,3,1,0),"Verlängerung","Batterie",500,"Erdzeichen")):
            with self.subTest(procedure=procedure,mode=mode,voltage=voltage):
                g=path(*route)
                self.assertEqual((g.step,g.procedure,g.mode,g.voltage),("start",procedure,mode,voltage))
                self.assertIn(key,g.instruction())
                self.assertIn("PASS",dict(g.choices()))
                self.assertFalse(g.stored)
                g.choose(3)
                self.assertEqual(g.step,"save")
                g.choose(0)
                self.assertEqual(g.examination()["voltage_confirmed"],voltage)

    def test_mains_and_voltage_confirmed_on_the_tester(self):
        g=path(0,0)
        self.assertEqual(g.step,"connect1")
        self.assertIn("Netz an 11 prüfen",g.instruction())
        self.assertIn("500 V am Tester prüfen",g.instruction())
        self.assertNotIn("250",g.instruction())
        self.assertIn("Abweichendes Verfahren",dict(g.choices()))
        self.assertIsNone(g.examination()["voltage_confirmed"])

    def test_low_load_explicit_check_then_correct_button_for_each_class(self):
        for number,art,key in ((0,"key_i","Erdzeichen"),(1,"key_ii","Doppelquadrat")):
            g=path(0,number,0,0)
            self.assertEqual(g.step,"low")
            self.assertIn("eingeschaltet",g.instruction())
            self.assertEqual(g.art,"lcd")
            self.assertFalse(g.stored)
            g.choose(0)
            self.assertEqual((g.step,g.art),("low_continue",art))
            self.assertIn(key,g.instruction())
            self.assertIn("erneut",g.instruction())
            self.assertIn("I LEAK blinkt",dict(g.choices()))
        self.assertEqual(path(0,0,0,0,1).step,"stop")

    def test_flashing_leak_requires_a_separate_safety_confirmation(self):
        g=path(0,1,0,1)
        self.assertEqual(g.step,"leak")
        self.assertIn("230 V",g.instruction())
        self.assertIn("ohne Erdpfad",g.instruction())
        self.assertEqual(g.art,"lcd")
        g.choose(0)
        self.assertEqual((g.step,g.art),("energise","key_leak"))
        g.choose(2)
        self.assertEqual(g.step,"running")
        self.assertIn("PASS",dict(g.choices()))
        self.assertEqual(path(0,1,1,1,1).step,"wrong")

    def test_warnings_and_fail_do_not_get_turned_into_pass(self):
        for route,expected in (((0,0,0,5),"high"),((0,0,0,6,0),"table"),
                               ((0,0,0,6,1),"hot"),((0,0,0,6,2),"wrong"),
                               ((0,1,0,6,0),"wrong"),((1,),"stop"),
                               ((2,),"stop"),((0,2,1),"stop"),((0,4),"special")):
            with self.subTest(expected=expected):
                g=path(*route)
                self.assertEqual(g.step,expected)
                self.assertFalse(g.stored)
                self.assertNotIn("PASS",dict(g.choices()))
        g=path(0,2,0,0,4)
        self.assertEqual(g.step,"save")
        self.assertIn("RISO",STEPS["save"].help)
        self.assertEqual(g.observed,"FAIL")
        g.choose(1)
        self.assertEqual(g.step,"unsaved")
        self.assertFalse(g.stored)

    def test_only_one_new_slot_compared_with_workflow_baseline_advances(self):
        old={"usb":(3,{"001":"a","002":"b"})}
        for current,slot in (({},None),({"usb":(3,{"001":"a","002":"b"})},None),
             ({"usb":(4,{"001":"a","002":"b"})},None),({"usb":(4,{"001":"c","002":"b"})},"001"),
             ({"usb":(4,{"001":"c","002":"d"})},None),({"usb":(4,{"001":"a"})},None),
             ({"rs232":(4,{"001":"c"})},None)):
            with self.subTest(current=current):
                source="rs232" if "rs232" in current else "usb"
                self.assertEqual(fresh_slot(old,source,current)[1],slot)
        self.assertEqual(fresh_slot({"rs232":(1,{"001":"a"})},"rs232",{"rs232":(4,{"001":"a","002":"b"})})[1],"002")


class OutputTests(unittest.TestCase):
    def test_omit_unused_but_keep_partial_and_failed_measurements(self):
        failed={"name":"RPE","value":">2,34","unit":"Ohm","result":"nicht bestanden"}
        partial={"name":"IPE","value":"<0,1","unit":None}
        report={"source":"BENNING","record":{"verdict":"nicht bestanden"},"import_source":"usb",
                "measurements":[{"name":"IBer"},failed,partial]}
        self.assertEqual(visible_measurements(report),[failed,partial])
        self.assertEqual(result_kind(report),"FAIL")
        self.assertEqual(measurement_summary(failed),("RPE",">2,34 Ohm","","nicht bestanden","FAIL"))
        self.assertEqual(measurement_summary(partial)[3],"unvollständig")
        report["record"]={"verdict":"bestanden"}
        self.assertEqual(result_kind(report),"PASS")
        self.assertTrue(electrical_check(report)[1])

    def test_rs232_keeps_limits_without_inventing_individual_verdicts(self):
        row={"name":"RISO","value":">19,99","unit":"MΩ","limit":"2,00","limit_unit":"MΩ"}
        self.assertEqual(measurement_summary(row),("RISO",">19,99 MΩ","2,00 MΩ","","unknown"))
        self.assertEqual(result_kind({"source":"BENNING","import_source":"rs232","record":{"verdict":"bestanden"},
                                      "measurements":[row]}),"PASS")
