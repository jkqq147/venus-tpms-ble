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
			description: qsTr("Status")
			item.bind: root.slotPrefix + "/StateText"
		}

		MbItemValue {
			description: qsTr("Sensor ID")
			item.bind: root.slotPrefix + "/SensorId"
		}

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
