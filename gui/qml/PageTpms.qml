import QtQuick 1.1
import com.victron.velib 1.0

MbPage {
	id: root
	title: qsTr("TPMS")

	model: VisibleItemModel {
		MbSubMenu {
			description: qsTr("Front left")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_left/PressureDisplay"; width: 92; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_left/TemperatureDisplay"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "front_left"; pageTitle: qsTr("Front left") } }
		}

		MbSubMenu {
			description: qsTr("Front right")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_right/PressureDisplay"; width: 92; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_right/TemperatureDisplay"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "front_right"; pageTitle: qsTr("Front right") } }
		}

		MbSubMenu {
			description: qsTr("Rear left")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_left/PressureDisplay"; width: 92; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_left/TemperatureDisplay"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "rear_left"; pageTitle: qsTr("Rear left") } }
		}

		MbSubMenu {
			description: qsTr("Rear right")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_right/PressureDisplay"; width: 92; height: 25 }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_right/TemperatureDisplay"; width: 82; height: 25 }
			subpage: Component { PageTpmsWheel { wheelKey: "rear_right"; pageTitle: qsTr("Rear right") } }
		}

		MbSubMenu {
			description: qsTr("Discover sensors")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/DiscoveredCount"; width: 92; height: 25 }
			subpage: Component { PageTpmsDiscovered {} }
		}

		MbSubMenu {
			description: qsTr("Diagnostics")
			item: VBusItem { value: [] }
			MbTextBlock { item.bind: "com.victronenergy.tpms.main/StatusText"; width: 110; height: 25 }
			subpage: Component { PageTpmsDiagnostics {} }
		}
	}
}
