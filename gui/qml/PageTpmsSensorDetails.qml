import QtQuick 1.1
import com.victron.velib 1.0

MbPage {
	id: root
	title: qsTr("Sensor details")

	property string slotPrefix: ""

	model: VisibleItemModel {
		MbItemValue {
			description: qsTr("Sensor ID")
			item.bind: root.slotPrefix + "/SensorId"
		}

		MbItemValue {
			description: qsTr("Battery")
			item {
				bind: root.slotPrefix + "/Battery"
				unit: "%"
			}
		}

		MbItemValue {
			description: qsTr("RSSI")
			item {
				bind: root.slotPrefix + "/Rssi"
				unit: "dBm"
			}
		}

		MbItemValue {
			description: qsTr("Last seen")
			item.bind: root.slotPrefix + "/LastSeen"
		}
	}
}
