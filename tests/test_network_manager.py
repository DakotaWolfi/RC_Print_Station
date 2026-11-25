"""Exercise NetworkManager transactions against a strict fake bus, no radio."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from station_network import Network, NetworkError, NetworkManager, ACTIVE


class DBusError(Exception):
    pass


class NetworkManagerTests(unittest.TestCase):
    def fake(self, state=2, activation_error=None):
        driver=NetworkManager()
        path="/active"
        root=Mock()
        root.AddAndActivateConnection2.return_value=("/profile",path,{})
        root.AddAndActivateConnection2.side_effect=activation_error
        dev=Mock()
        dev.Get.return_value="/previous"
        previous=Mock()
        previous.Get.return_value="/previous_profile"
        active=Mock()
        active.Get.return_value=state
        saved=Mock()
        bus=Mock()
        bus.get_object.side_effect=lambda name,path,**kwargs: {
            "/previous":previous,"/active":active,"/profile":saved}[path]
        dbus=SimpleNamespace(Interface=lambda obj,iface:obj,DBusException=DBusError,
                             ByteArray=bytes,UInt32=int)
        net=Network("/ap",b"Werkstatt",80,"WPA2","wpa-psk")
        driver._open=Mock(return_value=(dbus,bus))
        driver._device=Mock(return_value=(root,"/wlan",None,dev))
        driver._ap=Mock(return_value=net)
        return driver,net,root,active,saved,bus

    def test_activate_volatile_then_persist_with_autoconnect(self):
        driver,net,root,active,saved,bus=self.fake()
        with patch("station_network.wifi_address",return_value="192.168.2.4"):
            self.assertEqual(driver._connect(net,"dummy-password"),("Werkstatt","192.168.2.4"))
        args,kw=root.AddAndActivateConnection2.call_args
        self.assertEqual(args[1:],("/wlan","/ap",{"persist":"volatile"}))
        self.assertEqual(kw["signature"],"a{sa{sv}}ooa{sv}")
        self.assertEqual(args[0]["802-11-wireless-security"]["psk"],"dummy-password")
        self.assertFalse(args[0]["connection"]["autoconnect"])
        self.assertTrue(saved.Update2.call_args.args[0]["connection"]["autoconnect"])
        self.assertEqual(saved.Update2.call_args.args[1],1)
        root.DeactivateConnection.assert_not_called()
        bus.close.assert_called_once()

    def test_failed_activation_rolls_back_and_does_not_echo_secret(self):
        for state,error in ((4,None),(0,DBusError("dummy-password"))):
            with self.subTest(state=state):
                driver,net,root,active,saved,bus=self.fake(state,error)
                with self.assertRaises(NetworkError) as exc:
                    driver._connect(net,"dummy-password")
                self.assertNotIn("dummy-password",str(exc.exception))
                self.assertEqual(root.ActivateConnection.call_args.args,("/previous_profile","/wlan","/"))
                if error is None:
                    self.assertEqual(root.DeactivateConnection.call_args.args,("/active",))
                saved.Update2.assert_not_called()
                bus.close.assert_called_once()
