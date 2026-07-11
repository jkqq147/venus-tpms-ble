import QtQuick 1.1
import com.victron.velib 1.0

MbPage {
	id: root
	title: qsTr("TPMS")

	model: VisibleItemModel {
		MbSubMenu {
			description: qsTr("Front left")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_left/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_left/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_left/StateText"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "front_left"; pageTitle: qsTr("Front left") } }
		}

		MbSubMenu {
			description: qsTr("Front right")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_right/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_right/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_right/StateText"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "front_right"; pageTitle: qsTr("Front right") } }
		}

		MbSubMenu {
			description: qsTr("Rear left")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_left/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_left/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_left/StateText"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "rear_left"; pageTitle: qsTr("Rear left") } }
		}

		MbSubMenu {
			description: qsTr("Rear right")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_right/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_right/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_right/StateText"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "rear_right"; pageTitle: qsTr("Rear right") } }
		}

		MbItemValue {
			description: qsTr("Status")
			item.bind: "com.victronenergy.tpms.main/StatusText"
		}

		MbItemValue {
			description: qsTr("Bluetooth")
			item.bind: "com.victronenergy.tpms.main/Bluetooth/StatusText"
		}

		MbItemValue {
			description: qsTr("BLE devices")
			item.bind: "com.victronenergy.tpms.main/Bluetooth/DeviceCount"
		}

		MbItemValue {
			description: qsTr("BLE manufacturer data")
			item.bind: "com.victronenergy.tpms.main/Bluetooth/ManufacturerDataCount"
		}

		MbSubMenu {
			description: qsTr("Discovered 1")
			item: VBusItem { value: [] }
			property VBusItem discovered0Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/0/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/0/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/0/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/0/RssiDisplay"; width: 70; height: 25 }
			show: discovered0Name.valid && discovered0Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 0 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 2")
			item: VBusItem { value: [] }
			property VBusItem discovered1Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/1/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/1/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/1/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/1/RssiDisplay"; width: 70; height: 25 }
			show: discovered1Name.valid && discovered1Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 1 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 3")
			item: VBusItem { value: [] }
			property VBusItem discovered2Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/2/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/2/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/2/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/2/RssiDisplay"; width: 70; height: 25 }
			show: discovered2Name.valid && discovered2Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 2 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 4")
			item: VBusItem { value: [] }
			property VBusItem discovered3Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/3/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/3/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/3/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/3/RssiDisplay"; width: 70; height: 25 }
			show: discovered3Name.valid && discovered3Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 3 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 5")
			item: VBusItem { value: [] }
			property VBusItem discovered4Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/4/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/4/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/4/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/4/RssiDisplay"; width: 70; height: 25 }
			show: discovered4Name.valid && discovered4Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 4 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 6")
			item: VBusItem { value: [] }
			property VBusItem discovered5Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/5/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/5/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/5/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/5/RssiDisplay"; width: 70; height: 25 }
			show: discovered5Name.valid && discovered5Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 5 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 7")
			item: VBusItem { value: [] }
			property VBusItem discovered6Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/6/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/6/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/6/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/6/RssiDisplay"; width: 70; height: 25 }
			show: discovered6Name.valid && discovered6Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 6 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 8")
			item: VBusItem { value: [] }
			property VBusItem discovered7Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/7/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/7/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/7/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/7/RssiDisplay"; width: 70; height: 25 }
			show: discovered7Name.valid && discovered7Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 7 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 9")
			item: VBusItem { value: [] }
			property VBusItem discovered8Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/8/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/8/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/8/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/8/RssiDisplay"; width: 70; height: 25 }
			show: discovered8Name.valid && discovered8Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 8 } }
		}

		MbSubMenu {
			description: qsTr("Discovered 10")
			item: VBusItem { value: [] }
			property VBusItem discovered9Name: VBusItem { bind: "com.victronenergy.tpms.main/Discovered/9/Name" }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/9/PressureDisplay"; width: 78; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/9/TemperatureDisplay"; width: 70; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Discovered/9/RssiDisplay"; width: 70; height: 25 }
			show: discovered9Name.valid && discovered9Name.value !== ""
			subpage: Component { PageTpmsBind { sensorIndex: 9 } }
		}
	}
}
