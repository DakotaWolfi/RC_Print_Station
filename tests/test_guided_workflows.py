"""Cover the offline graph and its result semantics independently of the HMI."""
import unittest

from benning_guide import Guide, STEPS
from benning_output import measurement_summary, result_kind, visible_measurements
from benning_workflow import fresh_slot


def path(*choices):
    g=Guide()
    for choice in choices:
        if not g.choose(choice):
            raise AssertionError((g.step,choice))
    return g


class GuideTests(unittest.TestCase):
    def test_supported_procedures_start_and_complete_on_observed_pass(self):
        for route,procedure,mode,key in (
                ((0,0,0,0,0),"I","Batterie","Erdzeichen"),
                ((0,0,1,0,1),"I","Netz","Erdzeichen"),
                ((0,1,0,0,1),"II","Batterie","Doppelquadrat"),
                ((0,1,1,0,0),"II","Netz","Doppelquadrat"),
                ((0,2,0,0,0),"III","Batterie","Doppelquadrat"),
                ((0,3,0,0),"IEC","Batterie","Erdzeichen"),
                ((0,3,1,0),"Verlängerung","Batterie","Erdzeichen")):
            with self.subTest(procedure=procedure,mode=mode):
                g=path(*route)
                self.assertEqual((g.step,g.procedure,g.mode),("start",procedure,mode))
                self.assertIn(key,g.instruction())
                g.choose(0)
                self.assertEqual(g.step,"observed")
                self.assertFalse(g.stored)
                if mode=="Netz":
                    g.choose(2)
                    self.assertEqual(g.step,"leak")
                    g.choose(0)
                    self.assertEqual(g.step,"polarity")
                    g.choose(0)
                g.choose(0)
                self.assertEqual(g.step,"save")
                g.choose(0)
                self.assertEqual(g.step,"exam")
                self.assertEqual(g.examination()["status"],"Unvollständig")
                g.functional="Ohne Befund"
                self.assertEqual(g.examination("Prüfperson")["status"],"Erfasst")

    def test_warnings_stop_or_require_explicit_observation(self):
        normal=(0,0,1,0,0,0)
        for index,step in enumerate(("low","high","table","hot","wrong")):
            with self.subTest(step=step):
                g=path(*normal,3,index)
                self.assertEqual(g.step,step)
                self.assertFalse(g.stored)
                if step in ("low","table"):
                    self.assertTrue(g.choose(0))
                    self.assertEqual(g.step,"observed")
                    self.assertEqual(g.observed,"")
                else:
                    self.assertFalse(g.back())
                    self.assertFalse(g.choose(1))
                    g.choose(0)
                    self.assertEqual(g.examination()["status"],"Unvollständig")
        self.assertEqual(path(0,1,0,0,0,0,2).step,"wrong")
        self.assertEqual(path(0,1,1,0,0,0,3,2).step,"wrong")

    def test_failed_or_unavailable_measurement_is_not_reclassified(self):
        g=path(0,2,0,0,0,0,1)
        self.assertIn("RISO",g.instruction())
        self.assertEqual(g.observed,"FAIL")
        g.choose(0)
        g.choose(1)
        self.assertEqual(g.step,"unsaved")
        self.assertFalse(g.stored)
        g.choose(0)
        self.assertEqual(g.examination()["observed"],"FAIL")
        self.assertEqual(g.examination()["status"],"Unvollständig")

    def test_unclear_and_special_procedures_do_not_offer_a_start(self):
        for route,expected in (((1,),"stop"),((0,2,1),"stop"),((0,4),"special"),
                               ((0,0,2),"stop"),((0,3,1,1),"stop")):
            g=path(*route)
            self.assertEqual(g.step,expected)
            self.assertNotIn("start",[target for _,target in STEPS[g.step].choices])

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
        self.assertEqual(result_kind(report),"partial")

    def test_rs232_keeps_limits_without_inventing_individual_verdicts(self):
        row={"name":"RISO","value":">19,99","unit":"MΩ","limit":"2,00","limit_unit":"MΩ"}
        self.assertEqual(measurement_summary(row),("RISO",">19,99 MΩ","2,00 MΩ","","unknown"))
        self.assertEqual(result_kind({"source":"BENNING","import_source":"rs232","record":{"verdict":"bestanden"},
                                      "measurements":[row]}),"PASS")
