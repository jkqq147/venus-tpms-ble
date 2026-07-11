import QtQuick 1.1
import com.victron.velib 1.0

MbPage {
	id: root
	title: qsTr("Bind TPMS")

	property int sensorIndex: 0
	property string discoveredPrefix: "com.victronenergy.tpms.main/Discovered/" + sensorIndex

	model: VisibleItemModel {
		MbItemValue {
			description: qsTr("Name")
			item.bind: root.discoveredPrefix + "/Name"
		}

		MbItemValue {
			description: qsTr("Sensor ID")
			item.bind: root.discoveredPrefix + "/SensorId"
		}

		MbItemValue {
			description: qsTr("Pressure")
			item {
				bind: root.discoveredPrefix + "/Pressure"
				unit: "bar"
				decimals: 2
			}
		}

		MbItemValue {
			description: qsTr("Temperature")
			item {
				bind: root.discoveredPrefix + "/Temperature"
				unit: "C"
				decimals: 1
			}
		}

		MbItemOptions {
			description: qsTr("Wheel")
			bind: root.discoveredPrefix + "/AssignedWheel"
			possibleValues: [
				MbOption { description: qsTr("Unassigned"); value: "unassigned" },
				MbOption { description: qsTr("Front left"); value: "front_left" },
				MbOption { description: qsTr("Front right"); value: "front_right" },
				MbOption { description: qsTr("Rear left"); value: "rear_left" },
				MbOption { description: qsTr("Rear right"); value: "rear_right" }
			]
		}
	}
}
