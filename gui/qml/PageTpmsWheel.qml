import QtQuick 1.1
import com.victron.velib 1.0

MbPage {
	id: root
	title: pageTitle

	property string wheelKey: ""
	property string pageTitle: qsTr("TPMS")
	property string slotPrefix: "com.victronenergy.tpms.main/Slots/" + wheelKey

	model: VisibleItemModel {
		MbItemValue {
			description: qsTr("Pressure")
			item {
				bind: root.slotPrefix + "/Pressure"
				unit: "bar"
				decimals: 2
			}
		}

		MbItemValue {
			description: qsTr("Temperature")
			item {
				bind: root.slotPrefix + "/Temperature"
				unit: "C"
				decimals: 1
			}
		}

		MbItemValue {
			description: qsTr("Status")
			item.bind: root.slotPrefix + "/StateText"
		}

		MbSubMenu {
			description: qsTr("Sensor details")
			item: VBusItem { value: [] }
			subpage: Component { PageTpmsSensorDetails { slotPrefix: root.slotPrefix } }
		}
	}
}
